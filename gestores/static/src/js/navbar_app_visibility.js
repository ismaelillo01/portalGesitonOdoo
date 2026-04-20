/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { NavBar } from "@web/webclient/navbar/navbar";

const HIDDEN_APP_XMLIDS = new Set(["base.menu_management", "mail.menu_root_discuss"]);

patch(NavBar.prototype, {
    getVisibleAppsForGestores(apps = []) {
        if (!session.hide_case_manager_apps_sidebar) {
            return apps;
        }
        return apps.filter((app) => !HIDDEN_APP_XMLIDS.has(app.xmlid));
    },
});
