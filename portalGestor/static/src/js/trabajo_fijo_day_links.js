/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODEL = "portalgestor.trabajo_fijo";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.portalGestorFixedAction = useService("action");
        this.portalGestorFixedOrm = useService("orm");
        this.portalGestorFixedNotification = useService("notification");
        this.onPortalGestorFixedDayClick = this.onPortalGestorFixedDayClick.bind(this);
        onMounted(() => {
            this.rootRef.el?.addEventListener("click", this.onPortalGestorFixedDayClick);
        });
        onWillUnmount(() => {
            this.rootRef.el?.removeEventListener("click", this.onPortalGestorFixedDayClick);
        });
    },

    async onPortalGestorFixedDayClick(ev) {
        if (this.props.resModel !== TARGET_MODEL) {
            return;
        }
        const link = ev.target.closest(".o_portalgestor_fixed_grid_day_link");
        if (!link || !this.rootRef.el?.contains(link)) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();

        if (this.model.root.isNew || (await this.model.root.isDirty())) {
            const saved = await this.model.root.save({
                onError: (...args) => this.onSaveError(...args),
            });
            if (!saved) {
                return;
            }
        }

        const fixedId = Number.parseInt(this.model.root.resId || link.dataset.trabajoFijoId, 10);
        const date = link.dataset.date;
        if (!fixedId || !date) {
            this.portalGestorFixedNotification.add(
                _t("Guarda el trabajo fijo antes de abrir los tramos de un dia."),
                { type: "warning" }
            );
            return;
        }

        const action = await this.portalGestorFixedOrm.call(
            TARGET_MODEL,
            "action_open_day_lines",
            [[fixedId], date]
        );
        await this.portalGestorFixedAction.doAction(action, {
            onClose: async () => {
                if (this.props.resModel === TARGET_MODEL && this.model.root.resId === fixedId) {
                    await this.model.load({
                        resId: fixedId,
                        resIds: this.model.root.resIds,
                    });
                }
            },
        });
    },
});
