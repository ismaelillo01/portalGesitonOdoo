/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODEL = "portalgestor.trabajo_fijo";
const WIZARD_BUTTON_METHODS = new Set([
    "action_open_seed_wizard",
    "action_open_copy_week_wizard",
]);

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.portalGestorFixedAction = useService("action");
        this.portalGestorFixedOrm = useService("orm");
        this.portalGestorFixedNotification = useService("notification");
        this.onPortalGestorFixedClick = this.onPortalGestorFixedClick.bind(this);
        onMounted(() => {
            this.rootRef.el?.addEventListener("click", this.onPortalGestorFixedClick, true);
        });
        onWillUnmount(() => {
            this.rootRef.el?.removeEventListener("click", this.onPortalGestorFixedClick, true);
        });
    },

    async reloadPortalGestorFixedRecord(fixedId) {
        if (this.props.resModel === TARGET_MODEL && this.model.root.resId === fixedId) {
            await this.model.load({
                resId: fixedId,
                resIds: this.model.root.resIds,
            });
        }
    },

    async ensurePortalGestorFixedSaved() {
        if (this.model.root.isNew || (await this.model.root.isDirty())) {
            const saved = await this.model.root.save({
                onError: (...args) => this.onSaveError(...args),
            });
            if (!saved) {
                return false;
            }
        }
        return Number.parseInt(this.model.root.resId, 10) || false;
    },

    async openPortalGestorFixedAction(fixedId, action) {
        await this.portalGestorFixedAction.doAction(action, {
            onClose: async () => {
                await this.reloadPortalGestorFixedRecord(fixedId);
            },
        });
    },

    async onPortalGestorFixedClick(ev) {
        if (this.props.resModel !== TARGET_MODEL) {
            return;
        }
        const link = ev.target.closest(".o_portalgestor_fixed_grid_day_link");
        const wizardButton = ev.target.closest(
            "button[name='action_open_seed_wizard'], button[name='action_open_copy_week_wizard']"
        );
        if (
            (!link && !wizardButton) ||
            (link && !this.rootRef.el?.contains(link)) ||
            (wizardButton && !this.rootRef.el?.contains(wizardButton))
        ) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        ev.stopImmediatePropagation();

        const fixedId = await this.ensurePortalGestorFixedSaved();
        if (!fixedId) {
            return;
        }

        if (wizardButton) {
            const methodName = wizardButton.getAttribute("name");
            if (!WIZARD_BUTTON_METHODS.has(methodName)) {
                return;
            }
            const action = await this.portalGestorFixedOrm.call(TARGET_MODEL, methodName, [[fixedId]]);
            await this.openPortalGestorFixedAction(fixedId, action);
            return;
        }

        const date = link.dataset.date;
        if (!date) {
            this.portalGestorFixedNotification.add(_t("Guarda el trabajo fijo antes de abrir los tramos de un dia."), {
                type: "warning",
            });
            return;
        }
        const action = await this.portalGestorFixedOrm.call(
            TARGET_MODEL,
            "action_open_day_lines",
            [[fixedId], date]
        );
        await this.openPortalGestorFixedAction(fixedId, action);
    },
});
