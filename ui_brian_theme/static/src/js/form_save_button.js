/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

const PORTALGESTOR_MODELS_WITHOUT_SAVE_DISCARD = new Set([
    "portalgestor.asignacion",
    "portalgestor.asignacion.mensual",
]);

function usesPortalGestorVerificationFlow(resModel = "") {
    return PORTALGESTOR_MODELS_WITHOUT_SAVE_DISCARD.has(resModel);
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.uiBrianNotification = useService("notification");
    },

    get uiBrianShowSaveDiscardButtons() {
        const resModel = this.props.resModel || this.model?.root?.resModel || "";
        return !usesPortalGestorVerificationFlow(resModel);
    },

    async uiBrianManualSave(params = {}) {
        let failureAlreadyNotified = false;
        const saveParams = {
            ...params,
            onError: async (error, context) => {
                failureAlreadyNotified = true;
                this.uiBrianNotification.add(_t("Fallo al guardar."), {
                    type: "danger",
                });
                return this.onSaveError(error, context);
            },
        };

        try {
            const saved = await this.saveButtonClicked(saveParams);
            if (saved) {
                this.uiBrianNotification.add(_t("Guardado correctamente."), {
                    type: "success",
                });
            } else if (!failureAlreadyNotified) {
                this.uiBrianNotification.add(_t("Fallo al guardar."), {
                    type: "danger",
                });
            }
            return saved;
        } catch (error) {
            if (!failureAlreadyNotified) {
                this.uiBrianNotification.add(_t("Fallo al guardar."), {
                    type: "danger",
                });
            }
            throw error;
        }
    },
});

patch(FormViewDialog.prototype, {
    get uiBrianHideDialogFooter() {
        return usesPortalGestorVerificationFlow(this.props.resModel);
    },
});
