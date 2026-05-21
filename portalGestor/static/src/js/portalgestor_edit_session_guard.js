/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

const TARGET_MODELS = new Set([
    "portalgestor.asignacion",
    "portalgestor.asignacion.mensual",
    "portalgestor.trabajo_fijo",
]);
const TARGET_FIXED_MODEL = "portalgestor.asignacion.mensual";
const TARGET_FIXED_V2_MODEL = "portalgestor.trabajo_fijo";
const DELETE_ACTION_NAME = "action_eliminar_horario";
const DELETE_CONFIRM_WORD = "aceptar";

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

function isPortalGestorDeleteAction(controller, clickParams) {
    return Boolean(
        TARGET_MODELS.has(controller.props.resModel) &&
            clickParams?.type === "object" &&
            clickParams?.name === DELETE_ACTION_NAME
    );
}

class PortalGestorDeleteConfirmDialog extends Component {
    static template = "portalGestor.DeleteConfirmDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        confirm: Function,
        cancel: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({ value: "" });
        this.inputRef = useRef("confirmationInput");
        onMounted(() => this.inputRef.el?.focus());
    }

    get isConfirmed() {
        return this.state.value.trim().toLowerCase() === DELETE_CONFIRM_WORD;
    }

    onInput(ev) {
        this.state.value = ev.target.value;
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && this.isConfirmed) {
            ev.preventDefault();
            this.confirmDelete();
        }
    }

    confirmDelete() {
        if (!this.isConfirmed) {
            return;
        }
        this.props.confirm();
        this.props.close();
    }

    cancel() {
        this.props.cancel?.();
        this.props.close();
    }
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
        try {
            if (await this.model.root.isDirty()) {
                await this.model.root.discard();
            }
            await this.orm.call(this.props.resModel, "action_descartar_edicion", [[this.model.root.resId]]);
            if (this.props.resModel === TARGET_FIXED_MODEL || this.props.resModel === TARGET_FIXED_V2_MODEL) {
                await this.orm.call(this.props.resModel, "action_eliminar_borrador_no_verificado", [
                    [this.model.root.resId],
                ]);
            }
        } catch (e) {
            // Record may have been deleted by action_eliminar_horario;
            // silently ignore "record not found" errors during cleanup.
        }
    },

    async _confirmPortalGestorDelete() {
        return new Promise((resolve) => {
            let settled = false;
            const settle = (value) => {
                if (!settled) {
                    settled = true;
                    resolve(value);
                }
            };
            this.dialogService.add(
                PortalGestorDeleteConfirmDialog,
                {
                    confirm: () => settle(true),
                    cancel: () => settle(false),
                },
                { onClose: () => settle(false) }
            );
        });
    },

    async beforeExecuteActionButton(clickParams) {
        if (isPortalGestorDeleteAction(this, clickParams)) {
            const confirmed = await this._confirmPortalGestorDelete();
            if (!confirmed) {
                return false;
            }
        }
        return super.beforeExecuteActionButton(...arguments);
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
