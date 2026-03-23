/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FloatTimeField } from "@web/views/fields/float_time/float_time_field";
import { useEffect } from "@odoo/owl";

const TARGET_MODELS = new Set([
    "portalgestor.asignacion.linea",
    "portalgestor.asignacion.mensual.linea",
]);

function formatPortalGestorTimeInput(rawValue, inputType) {
    if (!/^\d+$/.test(rawValue || "") || rawValue.length < 2 || inputType?.startsWith("delete")) {
        return rawValue;
    }
    const hours = rawValue.slice(0, 2);
    const minutes = rawValue.slice(2, 4);
    return minutes ? `${hours}:${minutes}` : `${hours}:`;
}

function normalizePortalGestorTimeInput(rawValue) {
    const value = (rawValue || "").trim();
    if (!value) {
        return rawValue;
    }
    if (/^\d{3,4}$/.test(value)) {
        return `${value.slice(0, 2)}:${value.slice(2).padEnd(2, "0").slice(0, 2)}`;
    }
    const matches = value.match(/^(\d{1,2}):(\d*)$/);
    if (!matches) {
        return value;
    }
    const [, hours, minutes] = matches;
    return `${hours}:${minutes.padEnd(2, "0").slice(0, 2)}`;
}

function applyPortalGestorTimeValue(inputEl, nextValue) {
    if (!nextValue || nextValue === inputEl.value) {
        return;
    }
    inputEl.value = nextValue;
    try {
        inputEl.setSelectionRange(nextValue.length, nextValue.length);
    } catch {
        // The value change is still valid even if the browser cannot move the caret here.
    }
}

patch(FloatTimeField.prototype, {
    setup() {
        super.setup(...arguments);

        useEffect(
            (inputEl) => {
                if (!inputEl) {
                    return;
                }
                const resModel = this.props.record?.resModel;
                if (!TARGET_MODELS.has(resModel)) {
                    return;
                }

                const onInput = (ev) => {
                    applyPortalGestorTimeValue(
                        inputEl,
                        formatPortalGestorTimeInput(ev.target.value, ev.inputType)
                    );
                };
                const normalizeValue = () => {
                    applyPortalGestorTimeValue(
                        inputEl,
                        normalizePortalGestorTimeInput(inputEl.value)
                    );
                };
                const onKeydownCapture = (ev) => {
                    if (ev.key === "Tab" || ev.key === "Enter") {
                        normalizeValue();
                    }
                };

                inputEl.addEventListener("input", onInput);
                inputEl.addEventListener("blur", normalizeValue, true);
                inputEl.addEventListener("change", normalizeValue, true);
                inputEl.addEventListener("keydown", onKeydownCapture, true);
                return () => {
                    inputEl.removeEventListener("input", onInput);
                    inputEl.removeEventListener("blur", normalizeValue, true);
                    inputEl.removeEventListener("change", normalizeValue, true);
                    inputEl.removeEventListener("keydown", onKeydownCapture, true);
                };
            },
            () => [this.inputFloatTimeRef?.el]
        );
    },
});
