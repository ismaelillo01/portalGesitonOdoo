/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";

const PORTALGESTOR_USER_MODEL = "usuarios.usuario";
const PORTALGESTOR_USER_BADGE_CONTEXT_KEY = "portalgestor_show_user_group";
const PORTALGESTOR_USER_OPTION_TEMPLATE = "portalGestor.UserAutocompleteOption";

async function loadPortalGestorUserTypes(orm, userIds) {
    const ids = [...new Set((userIds || []).filter(Boolean))];
    if (!ids.length) {
        return {};
    }
    return orm.call(PORTALGESTOR_USER_MODEL, "get_portalgestor_user_types", [ids]);
}

patch(Many2XAutocomplete.prototype, {
    shouldUsePortalGestorUserBadges() {
        return (
            this.props.resModel === PORTALGESTOR_USER_MODEL &&
            Boolean(this.props.context?.[PORTALGESTOR_USER_BADGE_CONTEXT_KEY])
        );
    },

    get optionsSource() {
        const source = super.optionsSource;
        if (!this.shouldUsePortalGestorUserBadges()) {
            return source;
        }
        return {
            ...source,
            optionTemplate: PORTALGESTOR_USER_OPTION_TEMPLATE,
        };
    },

    async loadOptionsSource(request) {
        const options = await super.loadOptionsSource(...arguments);
        if (!this.shouldUsePortalGestorUserBadges()) {
            return options;
        }

        const typesByUserId = await loadPortalGestorUserTypes(
            this.orm,
            options.filter((option) => option.value && !option.action).map((option) => option.value)
        );

        for (const option of options) {
            if (!option.value || option.action) {
                continue;
            }
            option.resModel = this.props.resModel;
            option.portalGestorUserTypeBadge = typesByUserId[option.value]?.badge || "";
            option.portalGestorUserTypeLabel = typesByUserId[option.value]?.label || "";
        }

        return options;
    },
});
