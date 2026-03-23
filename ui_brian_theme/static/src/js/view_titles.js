/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";

const CUSTOM_MODEL_PREFIXES = [
    "portalgestor.",
    "trabajadores.",
    "usuarios.",
    "gestores.",
    "zonastrabajo.",
];

const TITLE_CONFIG = {
    "portalgestor.asignacion": {
        calendarBase: _t("Horarios"),
        calendarRelatedBase: _t("Horario"),
        calendarFilterFields: ["usuario_id", "trabajador_calendar_filter_id"],
        compactCalendarSearch: true,
        formBase: _t("Asignando Horario"),
        formField: "usuario_id",
        listBase: _t("Horarios"),
    },
    "portalgestor.asignacion.mensual": {
        formBase: _t("Asignando Horario"),
        formField: "usuario_id",
        listBase: _t("Horarios Fijos"),
    },
    "trabajadores.vacacion": {
        calendarBase: _t("Asignar Vacaciones"),
        calendarRelatedBase: _t("Asignar Vacaciones"),
        calendarFilterFields: ["trabajador_id"],
        compactCalendarSearch: true,
        formBase: _t("Asignar Vacaciones"),
        formField: "trabajador_id",
        listBase: _t("Asignar Vacaciones"),
    },
    "trabajadores.trabajador": {
        formBase: _t("AP"),
        formUseDisplayName: true,
        listBase: _t("APs"),
    },
    "usuarios.usuario": {
        formBase: _t("USUARIO"),
        formUseDisplayName: true,
        listBase: _t("USUARIOS"),
    },
};

function isCustomModel(resModel = "") {
    return CUSTOM_MODEL_PREFIXES.some((prefix) => resModel.startsWith(prefix));
}

function prettifyModelName(resModel = "") {
    const technicalName = resModel.split(".").pop() || resModel;
    return technicalName
        .split("_")
        .filter(Boolean)
        .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
        .join(" ");
}

function getTitleConfig(resModel) {
    return TITLE_CONFIG[resModel] || null;
}

function getMany2OneLabel(rawValue) {
    if (Array.isArray(rawValue)) {
        return rawValue[1] || "";
    }
    if (typeof rawValue === "string") {
        return rawValue;
    }
    return "";
}

function getRecordLabel(recordData, fieldName) {
    if (!recordData || !fieldName) {
        return "";
    }
    if (fieldName === "display_name") {
        return recordData.display_name || "";
    }
    return getMany2OneLabel(recordData[fieldName]);
}

function getSingleActiveFilter(filterSections, targetFields = []) {
    const matches = [];
    for (const section of filterSections || []) {
        if (targetFields.length && !targetFields.includes(section.fieldName)) {
            continue;
        }
        for (const filter of section.filters || []) {
            if (!filter.active || filter.type === "all" || !filter.label) {
                continue;
            }
            matches.push({
                fieldName: section.fieldName,
                label: filter.label,
            });
        }
    }
    if (matches.length !== 1) {
        return null;
    }
    return matches[0];
}

function getBaseTitle(resModel, viewType) {
    const config = getTitleConfig(resModel);
    const configuredTitle = config?.[`${viewType}Base`];
    if (configuredTitle) {
        return configuredTitle;
    }
    if (isCustomModel(resModel)) {
        return prettifyModelName(resModel);
    }
    return "";
}

function getRelationDescriptor(fieldName, label) {
    if (!fieldName || !label) {
        return "";
    }
    if (fieldName.includes("usuario")) {
        return _t("del USUARIO %s", label);
    }
    if (fieldName.includes("trabajador")) {
        return _t("del AP %s", label);
    }
    return label;
}

function buildRelatedTitle(baseTitle, fieldName, label) {
    const descriptor = getRelationDescriptor(fieldName, label);
    return descriptor ? `${baseTitle} ${descriptor}` : baseTitle;
}

function getFormTitle(resModel, recordData) {
    const config = getTitleConfig(resModel);
    const baseTitle = getBaseTitle(resModel, "form");
    if (!baseTitle) {
        return "";
    }
    const relatedLabel = getRecordLabel(recordData, config?.formField);
    if (relatedLabel && config?.formField) {
        return buildRelatedTitle(baseTitle, config.formField, relatedLabel);
    }
    const displayLabel = config?.formUseDisplayName ? recordData?.display_name || "" : "";
    return displayLabel ? `${baseTitle} ${displayLabel}` : baseTitle;
}

function getListTitle(resModel) {
    return getBaseTitle(resModel, "list");
}

function getCalendarTitle(resModel, filterSections) {
    const config = getTitleConfig(resModel);
    const baseTitle = getBaseTitle(resModel, "calendar");
    if (!baseTitle) {
        return "";
    }
    const activeFilter = getSingleActiveFilter(filterSections, config?.calendarFilterFields || []);
    if (activeFilter && config?.calendarRelatedBase) {
        return buildRelatedTitle(config.calendarRelatedBase, activeFilter.fieldName, activeFilter.label);
    }
    return baseTitle;
}

function usesCompactCalendarSearch(resModel) {
    return Boolean(getTitleConfig(resModel)?.compactCalendarSearch);
}

function usesCompactListSearch(resModel) {
    return isCustomModel(resModel);
}

patch(FormController.prototype, {
    get uiBrianViewTitle() {
        return getFormTitle(this.props.resModel, this.model?.root?.data);
    },
});

patch(ListController.prototype, {
    get uiBrianViewTitle() {
        return getListTitle(this.props.resModel);
    },

    get uiBrianUseCompactListSearch() {
        return usesCompactListSearch(this.props.resModel);
    },
});

patch(CalendarController.prototype, {
    get uiBrianViewTitle() {
        return getCalendarTitle(this.props.resModel, this.model?.filterSections);
    },

    get uiBrianUseCompactCalendarSearch() {
        return usesCompactCalendarSearch(this.props.resModel);
    },
});
