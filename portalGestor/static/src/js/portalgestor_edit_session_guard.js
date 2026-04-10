/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

const TARGET_MODELS = new Set([
    "portalgestor.asignacion",
    "portalgestor.asignacion.mensual",
    "portalgestor.trabajo_fijo",
]);
const TARGET_FIXED_MODEL = "portalgestor.asignacion.mensual";
const TARGET_FIXED_V2_MODEL = "portalgestor.trabajo_fijo";

function isPortalGestorExistingRecord(controller) {
    return Boolean(
        TARGET_MODELS.has(controller.props.resModel) &&
            controller.model?.root?.resId
    );
}

function shouldWarnBeforePortalGestorUnload(controller) {
    return Boolean(
        isPortalGestorExistingRecord(controller) &&
            (
                controller.model?.root?.data?.edit_session_pending ||
                controller.model?.root?.data?.confirmado === false
            )
    );
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.portalGestorLeaveHandled = false;
    },

    async _cleanupPortalGestorLeave() {
        if (this.portalGestorLeaveHandled || !isPortalGestorExistingRecord(this)) {
            return;
        }
        this.portalGestorLeaveHandled = true;
        if (await this.model.root.isDirty()) {
            await this.model.root.discard();
        }
        await this.orm.call(this.props.resModel, "action_descartar_edicion", [[this.model.root.resId]]);
        if (this.props.resModel === TARGET_FIXED_MODEL || this.props.resModel === TARGET_FIXED_V2_MODEL) {
            await this.orm.call(this.props.resModel, "action_eliminar_borrador_no_verificado", [
                [this.model.root.resId],
            ]);
        }
    },

    async beforeLeave() {
        if (isPortalGestorExistingRecord(this)) {
            await this._cleanupPortalGestorLeave();
            return;
        }
        return super.beforeLeave(...arguments);
    },

    async beforeUnload(ev) {
        if (shouldWarnBeforePortalGestorUnload(this)) {
            ev.preventDefault();
            ev.returnValue = "Unsaved changes";
            return;
        }
        return super.beforeUnload(...arguments);
    },

    async discard() {
        if (isPortalGestorExistingRecord(this)) {
            await this._cleanupPortalGestorLeave();
            if (this.props.onDiscard) {
                this.props.onDiscard(this.model.root);
            }
            if (this.model.root.isNew || this.env.inDialog) {
                this.env.config.historyBack();
            }
            return;
        }
        return super.discard(...arguments);
    },
});

patch(FormViewDialog.prototype, {
    async discardRecord() {
        if (TARGET_MODELS.has(this.props.resModel)) {
            const beforeLeaveCallbacks = this.viewProps.__beforeLeave__.callbacks;
            const results = await Promise.all(beforeLeaveCallbacks.map((callback) => callback()));
            if (results.includes(false)) {
                return;
            }
        }
        return super.discardRecord(...arguments);
    },
});
