/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const PORTALGESTOR_MENU_XMLID = "portalGestor.portalgestor_menu_asignaciones";
const PORTALGESTOR_ACTION_XMLID = "portalGestor.action_portalgestor_asignacion";

export class UiBrianNavbarHomeButton extends Component {
    static template = "ui_brian_theme.NavbarHomeButton";
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
    }

    async goToPortalGestor() {
        const targetMenu = this.menuService
            .getAll()
            .find((menu) => menu.xmlid === PORTALGESTOR_MENU_XMLID && menu.actionID);
        if (targetMenu) {
            await this.menuService.selectMenu(targetMenu);
            return;
        }
        await this.actionService.doAction(PORTALGESTOR_ACTION_XMLID, {
            clearBreadcrumbs: true,
        });
    }
}

registry.category("systray").add(
    "ui_brian_theme.home_button",
    {
        Component: UiBrianNavbarHomeButton,
        isDisplayed: (env) => !env.isSmall,
    },
    { sequence: 26 }
);
