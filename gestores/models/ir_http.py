# -*- coding: utf-8 -*-
from odoo import models


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        session_info = super().session_info()
        session_info['hide_case_manager_apps_sidebar'] = bool(
            self.env.user._is_internal() and self.env.user._should_hide_case_manager_apps_sidebar()
        )
        return session_info
