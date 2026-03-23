/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.uiBrianNotification = useService("notification");
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
