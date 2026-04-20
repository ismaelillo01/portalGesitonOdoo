/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class UiBrianNavbarHomeButton extends Component {
    static template = "ui_brian_theme.NavbarHomeButton";
    static props = {};

    goToPortalHome() {
        browser.location.href = "/portal-inicio";
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
