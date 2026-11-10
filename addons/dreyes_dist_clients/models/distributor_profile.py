# -*- coding: utf-8 -*-
import base64
import binascii
import mimetypes

from werkzeug.utils import secure_filename

from odoo import _, fields, models
from odoo.exceptions import UserError


class DreyesDistributorProfile(models.Model):
    _inherit = "dreyes.distributor.profile"

    request_count = fields.Integer(string="Solicitudes", default=1, readonly=True)
    contact_email = fields.Char(string="Correo", related="partner_id.email", store=True, readonly=False)
    contact_phone = fields.Char(string="Teléfono", related="partner_id.phone", store=True, readonly=False)
    city = fields.Char(string="Ciudad", related="partner_id.city", store=True, readonly=False)
    state_id = fields.Many2one("res.country.state", string="Estado/Provincia", related="partner_id.state_id", store=True, readonly=False)
    country_id = fields.Many2one("res.country", string="País", related="partner_id.country_id", store=True, readonly=False)
    contact_first_name = fields.Char(string="Nombre", related="partner_id.first_name", readonly=False)
    contact_last_name = fields.Char(string="Apellido", related="partner_id.last_name", readonly=False)
    street = fields.Char(string="Dirección", related="partner_id.street", readonly=False)
    street2 = fields.Char(string="Dirección adicional", related="partner_id.street2", readonly=False)
    zip = fields.Char(string="Código postal", related="partner_id.zip", readonly=False)
    tax_permit_file = fields.Binary(
        string="Tax permit vigente", related="current_permit_id.attachment_id.datas", readonly=True,
    )
    tax_permit_filename = fields.Char(related="current_permit_id.filename", readonly=True)

    def action_upload_tax_permit(self):
        self.ensure_one()
        self._check_reviewer()
        self.check_access("write")
        return {
            "type": "ir.actions.act_window", "name": _("Subir tax permit"),
            "res_model": "dreyes.distributor.permit.upload", "view_mode": "form",
            "target": "new", "context": {"default_profile_id": self.id},
        }

    def action_send_to_review(self):
        self._check_reviewer()
        self.write({
            "state": "under_review", "submitted_at": fields.Datetime.now(),
            "submitted_by_id": self.env.user.id, "reviewed_at": False,
            "reviewed_by_id": False, "approved_at": False,
            "approved_by_id": False, "correction_reason": False,
        })
        return True

    def action_reset_profile(self):
        self._check_reviewer()
        self.write({
            "state": "no_profile", "submitted_at": False, "submitted_by_id": False,
            "reviewed_at": False, "reviewed_by_id": False,
            "approved_at": False, "approved_by_id": False,
            "correction_reason": False,
        })
        return True

    def action_approve(self):
        self._check_reviewer()
        for profile in self:
            missing = profile._required_missing_labels()
            if missing:
                raise UserError(_("Faltan datos obligatorios: %s") % ", ".join(missing))
            if not profile.segment_id.active or not profile.segment_id.pricelist_id.active:
                raise UserError(_("Debe asignar un segmento y una lista de precios activos."))
        return super().action_approve()


class DreyesDistributorPermitUpload(models.TransientModel):
    _name = "dreyes.distributor.permit.upload"
    _description = "Subir tax permit desde el backend"

    profile_id = fields.Many2one("dreyes.distributor.profile", required=True, readonly=True)
    filename = fields.Char(required=True)
    file = fields.Binary(string="Archivo", required=True, attachment=False)

    def action_upload(self):
        self.ensure_one()
        profile = self.profile_id.exists()
        profile._check_reviewer()
        profile.check_access("write")
        if not profile:
            raise UserError(_("El expediente ya no existe."))
        filename = secure_filename(self.filename or "")
        extension = filename.rsplit(".", 1)[-1].lower()
        if extension not in {"pdf", "jpg", "jpeg", "png"}:
            raise UserError(_("El tax permit debe ser un archivo PDF, JPG, JPEG o PNG."))
        try:
            data = base64.b64decode(self.file or b"", validate=True)
        except (ValueError, binascii.Error):
            raise UserError(_("El archivo del tax permit no es válido."))
        if not data:
            raise UserError(_("El archivo del tax permit está vacío."))
        if len(data) > 15 * 1024 * 1024:
            raise UserError(_("El tax permit debe pesar 15 MB o menos."))
        attachment = self.env["ir.attachment"].create({
            "name": filename, "datas": base64.b64encode(data),
            "mimetype": mimetypes.guess_type(filename)[0],
            "res_model": profile._name, "res_id": profile.id, "public": False,
        })
        # Reviewers may upload versions, but cannot edit or delete permit history.
        permit = self.env["dreyes.distributor.permit"].sudo().create({
            "profile_id": profile.id, "attachment_id": attachment.id,
            "filename": filename, "mimetype": attachment.mimetype,
            "uploaded_by_id": self.env.user.id,
        })
        profile.write({"current_permit_id": permit.id})
        if profile.state in ("approved", "pending_approval"):
            profile.action_send_to_review()
        return {"type": "ir.actions.act_window_close"}
