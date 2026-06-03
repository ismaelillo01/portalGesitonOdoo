/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { Component, useEffect } from "@odoo/owl";

const BAJA_MODEL = "usuarios.usuario";

/**
 * Formatea una fecha ISO (YYYY-MM-DD) como DD/MM/YYYY para mostrar al usuario.
 */
function formatDateDisplay(isoDate) {
    if (!isoDate) return "";
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
}

/**
 * Diálogo de aviso que aparece al activar la baja de un usuario.
 * Solo informa — Continuar deja todo como está, Cancelar revierte baja.
 */
class BajaWarningDialog extends Component {
    static template = "portalGestor.BajaWarningDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        confirm: Function,
        cancel: Function,
        fechaBaja: String,
    };

    onConfirm() {
        this.props.confirm();
        this.props.close();
    }

    onCancel() {
        this.props.cancel();
        this.props.close();
    }
}

/**
 * Patch del FormController para detectar cuando el campo `baja` de
 * usuarios.usuario cambia de False a True (acción del usuario, no carga
 * inicial) y mostrar el diálogo de aviso.
 */
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        // Solo aplica al modelo de usuarios
        if (this.props.resModel !== BAJA_MODEL) {
            return;
        }

        this._bajaDialogService = useService("dialog");

        // Último resId procesado (detectar navegación entre registros)
        this._bajaTrackedResId = undefined;
        // Valor de baja tal como está en el servidor (guardado)
        this._bajaCommittedValue = false;
        // ¿Ya se mostró el diálogo para el cambio en curso?
        this._bajaDialogShown = false;

        useEffect(
            () => {
                const record = this.model?.root;
                if (!record?.data) {
                    return;
                }

                const resId = record.resId;
                const currentBaja = !!record.data.baja;

                // Navegación a otro registro o primera carga: reiniciar estado
                if (this._bajaTrackedResId !== resId) {
                    this._bajaTrackedResId = resId;
                    this._bajaCommittedValue = currentBaja;
                    this._bajaDialogShown = false;
                    return;
                }

                // baja pasa de False (valor guardado) a True (cambio del usuario)
                if (currentBaja && !this._bajaCommittedValue && !this._bajaDialogShown) {
                    this._bajaDialogShown = true;

                    // fecha_baja ya debería estar seteada por el @api.onchange
                    const fechaRaw = record.data.fecha_baja;
                    const fechaDisplay = fechaRaw
                        ? formatDateDisplay(fechaRaw)
                        : formatDateDisplay(new Date().toISOString().slice(0, 10));

                    this._bajaDialogService.add(BajaWarningDialog, {
                        fechaBaja: fechaDisplay,
                        confirm: () => {
                            // El usuario acepta el aviso — no hace falta hacer nada,
                            // el guardado procesará baja + fecha_baja
                        },
                        cancel: () => {
                            // El usuario cancela — revertir baja y fecha_baja
                            this._bajaDialogShown = false;
                            record.update({ baja: false, fecha_baja: false });
                        },
                    });
                }

                // Si baja vuelve a False (el usuario desmarcó), limpiar estado
                if (!currentBaja) {
                    this._bajaDialogShown = false;
                }
            },
            () => [this.model?.root?.data?.baja, this.model?.root?.resId]
        );
    },

    /**
     * Tras guardar correctamente, actualizar el valor "committed" de baja
     * para que el próximo cambio vuelva a disparar el diálogo si fuera necesario.
     */
    async saveRecord(...args) {
        const result = await super.saveRecord(...args);
        if (this.props.resModel === BAJA_MODEL && this.model?.root) {
            this._bajaCommittedValue = !!this.model.root.data?.baja;
            this._bajaDialogShown = false;
        }
        return result;
    },
});
