# -*- coding: utf-8 -*-
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


PROFILE_STATES = [
    ("no_profile", "Sin perfil"),
    ("under_review", "En revisión"),
    ("pending_approval", "Pendiente de aprobación"),
    ("approved", "Aprobado"),
]


class DreyesMarketSegment(models.Model):
    _name = "dreyes.market.segment"
    _description = "Segmento de mercado de distribución"
    _order = "company_id, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    pricelist_id = fields.Many2one(
        "product.pricelist", required=True, check_company=True,
        domain="[('company_id', 'in', [False, company_id])]",
    )
    profile_ids = fields.One2many("dreyes.distributor.profile", "segment_id")
    approved_profile_count = fields.Integer(compute="_compute_approved_profile_count")

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "El nombre del segmento debe ser único por compañía."),
    ]

    @api.depends("profile_ids.state")
    def _compute_approved_profile_count(self):
        for segment in self:
            segment.approved_profile_count = len(segment.profile_ids.filtered(lambda p: p.state == "approved"))

    @api.constrains("company_id", "pricelist_id")
    def _check_pricelist_company(self):
        for segment in self:
            if segment.pricelist_id.company_id and segment.pricelist_id.company_id != segment.company_id:
                raise ValidationError(_("La lista de precios debe pertenecer a la misma compañía del segmento."))

    def write(self, vals):
        if vals.get("active") is False and any(self.mapped("approved_profile_count")):
            raise UserError(_("No se puede archivar un segmento utilizado por clientes aprobados."))
        pricelist_changed = "pricelist_id" in vals
        result = super().write(vals)
        if pricelist_changed:
            for segment in self:
                segment.profile_ids.filtered(lambda p: p.state == "approved")._activate_pricelist()
        return result

    def unlink(self):
        if any(self.mapped("profile_ids")):
            raise UserError(_("No se puede eliminar un segmento que tiene expedientes asociados; archívelo."))
        return super().unlink()


class DreyesDistributorProfile(models.Model):
    _name = "dreyes.distributor.profile"
    _description = "Expediente de distribuidor"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "write_date desc"
    _rec_name = "legal_business_name"
    _check_company_auto = True

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, index=True, tracking=True)
    website_id = fields.Many2one("website", required=True, ondelete="restrict")
    state = fields.Selection(PROFILE_STATES, required=True, default="no_profile", tracking=True, index=True)
    segment_id = fields.Many2one(
        "dreyes.market.segment", tracking=True, check_company=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    legal_business_name = fields.Char(tracking=True)
    ein = fields.Char(string="EIN", groups="dreyes_dist.group_distribution_reviewer")
    tax_permit_number = fields.Char(string="Número de permiso de Texas", tracking=True)
    permit_ids = fields.One2many("dreyes.distributor.permit", "profile_id", string="Historial de permisos")
    current_permit_id = fields.Many2one("dreyes.distributor.permit", string="Permiso vigente", tracking=True, copy=False)
    correction_reason = fields.Text(string="Correcciones solicitadas", tracking=True)
    submitted_at = fields.Datetime(copy=False, tracking=True)
    submitted_by_id = fields.Many2one("res.users", copy=False)
    reviewed_at = fields.Datetime(copy=False, tracking=True)
    reviewed_by_id = fields.Many2one("res.users", copy=False)
    approved_at = fields.Datetime(copy=False, tracking=True)
    approved_by_id = fields.Many2one("res.users", copy=False)
    is_complete = fields.Boolean(compute="_compute_is_complete")
    can_purchase = fields.Boolean(compute="_compute_can_purchase")

    _sql_constraints = [
        ("partner_company_uniq", "unique(partner_id, company_id)", "Ya existe un expediente para este cliente y compañía."),
    ]

    @api.depends(
        "legal_business_name", "ein", "tax_permit_number", "current_permit_id",
        "partner_id.first_name", "partner_id.last_name", "partner_id.street", "partner_id.city",
        "partner_id.state_id", "partner_id.zip", "partner_id.country_id", "partner_id.phone", "partner_id.email",
    )
    def _compute_is_complete(self):
        for profile in self:
            partner = profile.partner_id
            profile.is_complete = all([
                profile.legal_business_name, profile.ein, profile.tax_permit_number, profile.current_permit_id,
                partner.first_name, partner.last_name, partner.street, partner.city, partner.state_id,
                partner.zip, partner.country_id, partner.phone, partner.email,
            ])

    @api.depends("state", "segment_id", "segment_id.active", "segment_id.pricelist_id", "segment_id.pricelist_id.active")
    def _compute_can_purchase(self):
        for profile in self:
            profile.can_purchase = bool(
                profile.state == "approved" and profile.segment_id.active and profile.segment_id.pricelist_id.active
                and (not profile.segment_id.pricelist_id.company_id or profile.segment_id.pricelist_id.company_id == profile.company_id)
            )

    @api.constrains("ein", "tax_permit_number")
    def _check_tax_numbers(self):
        for profile in self:
            if profile.ein and not re.fullmatch(r"\d{9}", profile.ein):
                raise ValidationError(_("El EIN debe contener exactamente 9 dígitos."))
            if profile.tax_permit_number and not re.fullmatch(r"\d{11}", profile.tax_permit_number):
                raise ValidationError(_("El número del permiso de Texas debe contener exactamente 11 dígitos."))

    @api.constrains("company_id", "website_id", "segment_id")
    def _check_company_links(self):
        for profile in self:
            if profile.website_id.company_id != profile.company_id:
                raise ValidationError(_("El sitio web y el expediente deben pertenecer a la misma compañía."))
            if profile.segment_id and profile.segment_id.company_id != profile.company_id:
                raise ValidationError(_("El segmento y el expediente deben pertenecer a la misma compañía."))

    def _check_reviewer(self):
        if not self.env.user.has_group("dreyes_dist.group_distribution_reviewer"):
            raise UserError(_("No tiene permisos para procesar expedientes de distribución."))

    def _required_missing_labels(self):
        self.ensure_one()
        partner = self.partner_id
        values = [
            (self.legal_business_name, _("Nombre legal de la empresa")),
            (partner.first_name, _("Nombre")), (partner.last_name, _("Apellido")),
            (partner.email, _("Correo electrónico")), (partner.street, _("Dirección")),
            (partner.city, _("Ciudad")), (partner.state_id, _("Estado")),
            (partner.zip, _("Código postal")), (partner.country_id, _("País")),
            (partner.phone, _("Teléfono")), (self.ein, _("EIN")),
            (self.tax_permit_number, _("Número de permiso de Texas")),
            (self.current_permit_id, _("Archivo del tax permit")),
        ]
        return [label for value, label in values if not value]

    def _notify(self, recipients, subject, body):
        emails = ",".join(filter(None, recipients))
        if emails:
            self.env["mail.mail"].sudo().create({
                "subject": subject, "body_html": Markup("<p>%s</p>") % escape(body), "email_to": emails,
                "email_from": self.company_id.email or self.env.user.email_formatted or "noreply@localhost",
            })

    def _reviewer_emails(self):
        group = self.env.ref("dreyes_dist.group_distribution_reviewer")
        return group.users.filtered(lambda u: self.company_id in u.company_ids).mapped("partner_id.email")

    def notify_reviewers(self, subject, message):
        for profile in self:
            profile._notify(profile._reviewer_emails(), subject, message)

    def notify_customer(self, subject, message):
        for profile in self:
            profile._notify([profile.partner_id.email], subject, message)

    def action_mark_reviewed(self):
        self._check_reviewer()
        for profile in self:
            if profile.state != "under_review":
                raise UserError(_("Sólo los expedientes en revisión pueden marcarse como revisados."))
            missing = profile._required_missing_labels()
            if missing:
                raise UserError(_("Faltan datos obligatorios: %s") % ", ".join(missing))
            if not profile.segment_id or not profile.segment_id.active:
                raise UserError(_("Debe asignar un segmento de mercado activo."))
            profile.write({
                "state": "pending_approval", "reviewed_at": fields.Datetime.now(),
                "reviewed_by_id": self.env.user.id, "correction_reason": False,
            })
            profile.notify_customer(_("Perfil pendiente de aprobación"), _("Su perfil fue revisado y está pendiente de aprobación final."))

    def action_approve(self):
        self._check_reviewer()
        for profile in self:
            if profile.state != "pending_approval":
                raise UserError(_("Sólo los expedientes pendientes de aprobación pueden aprobarse."))
            if not profile.segment_id or not profile.segment_id.pricelist_id:
                raise UserError(_("El segmento debe tener una lista de precios válida."))
            profile.write({
                "state": "approved", "approved_at": fields.Datetime.now(),
                "approved_by_id": self.env.user.id, "correction_reason": False,
            })
            profile._activate_pricelist()
            profile.notify_customer(_("Cuenta de distribución aprobada"), _("Su cuenta fue aprobada. Ya puede consultar precios y comprar."))

    def action_request_corrections(self):
        self._check_reviewer()
        for profile in self:
            if not (profile.correction_reason or "").strip():
                raise UserError(_("Escriba las correcciones solicitadas antes de devolver el expediente."))
            profile.write({"state": "no_profile", "approved_at": False, "approved_by_id": False})
            profile.notify_customer(
                _("Correcciones requeridas en su perfil"),
                _("Revise su perfil. Correcciones solicitadas: %s") % profile.correction_reason,
            )

    def _activate_pricelist(self):
        for profile in self.filtered("can_purchase"):
            pricelist = profile.segment_id.pricelist_id
            commercial_partner = profile.partner_id.commercial_partner_id.sudo().with_company(profile.company_id)
            commercial_partner.property_product_pricelist = pricelist
            orders = self.env["sale.order"].sudo().search([
                ("partner_id", "child_of", commercial_partner.id), ("state", "=", "draft"),
                ("website_id.company_id", "=", profile.company_id.id),
            ])
            for order in orders:
                order._cart_update_pricelist(pricelist.id)

    def write(self, vals):
        segment_changed = "segment_id" in vals
        previously_approved = self.filtered(lambda p: p.state == "approved") if segment_changed else self.browse()
        result = super().write(vals)
        if segment_changed:
            demoted = previously_approved.filtered(lambda p: p.state == "approved")
            if demoted:
                super(DreyesDistributorProfile, demoted).write({
                    "state": "pending_approval", "approved_at": False, "approved_by_id": False,
                })
        return result


class DreyesDistributorPermit(models.Model):
    _name = "dreyes.distributor.permit"
    _description = "Versión de tax permit"
    _order = "uploaded_at desc, id desc"

    profile_id = fields.Many2one("dreyes.distributor.profile", required=True, ondelete="cascade", index=True)
    attachment_id = fields.Many2one("ir.attachment", required=True, ondelete="restrict")
    filename = fields.Char(required=True)
    mimetype = fields.Char()
    uploaded_at = fields.Datetime(required=True, default=fields.Datetime.now)
    uploaded_by_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
