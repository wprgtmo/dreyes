# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDistributionClientsApplication(TransactionCase):
    def test_root_menu_uses_application_icon(self):
        menu = self.env.ref(
            "dreyes_dist_clients.menu_distribution_clients_root"
        )
        self.assertEqual(
            menu.web_icon,
            "dreyes_dist_clients,static/description/icon.png",
        )

    def test_main_action_contains_all_requested_views(self):
        action = self.env.ref("dreyes_dist_clients.action_distribution_clients_all")
        self.assertEqual(action.view_mode, "kanban,list,form,graph,pivot")
        self.assertEqual(
            set(action.view_ids.mapped("view_mode")),
            {"kanban", "list", "form", "graph", "pivot"},
        )

    def test_pending_action_uses_workflow_domain_and_views(self):
        action = self.env.ref("dreyes_dist_clients.action_distribution_clients_pending")
        self.assertIn("under_review", action.domain)
        self.assertIn("pending_approval", action.domain)
        self.assertEqual(
            set(action.view_ids.mapped("view_mode")),
            {"kanban", "list", "form", "graph", "pivot"},
        )

    def test_analysis_measure_and_admin_access(self):
        profile = self.env["dreyes.distributor.profile"].new({})
        self.assertEqual(profile.request_count, 1)
        self.assertTrue(self.env.ref("base.user_admin").has_group("dreyes_dist.group_distribution_reviewer"))
