# -*- coding: utf-8 -*-
{
    "name": "UI Brian Theme",
    "summary": "Safe visual theme for Odoo 18 based on Brian mockups",
    "description": """
Non-intrusive visual theme for Odoo 18.
- Does not modify the DOM or structural QWeb templates.
- Restyles login, backend surfaces and portalGestor colors.
- Uses SCSS assets and safe decorative backgrounds only.
""",
    "author": "My Company",
    "license": "LGPL-3",
    "category": "Hidden",
    "version": "18.0.1.0.0",
    "depends": ["web"],
    "assets": {
        "web.assets_frontend": [
            "ui_brian_theme/static/src/js/portal_internal_carousel.js",
            "ui_brian_theme/static/src/scss/login_theme.scss",
            "ui_brian_theme/static/src/scss/portal_internal.scss",
        ],
        "web.assets_backend": [
            "ui_brian_theme/static/src/js/datetime_picker_tweaks.js",
            "ui_brian_theme/static/src/js/view_titles.js",
            "ui_brian_theme/static/src/js/form_save_button.js",
            "ui_brian_theme/static/src/js/navbar_home_button.js",
            "ui_brian_theme/static/src/js/list_renderer_fill.js",
            "ui_brian_theme/static/src/scss/backend_theme.scss",
            "ui_brian_theme/static/src/xml/view_titles.xml",
            "ui_brian_theme/static/src/xml/form_save_button.xml",
            "ui_brian_theme/static/src/xml/navbar_home_button.xml",
        ],
    },
    "installable": True,
    "application": False,
}
