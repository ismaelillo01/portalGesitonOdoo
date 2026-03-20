/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";

const PORTALGESTOR_RES_MODEL = "portalgestor.asignacion";
const COLOR_PRIORITY = {
    10: 0, // Verde: primero
    3: 1, // Amarillo: segundo
    1: 2, // Rojo: ultimo
};

function getCalendarPriority(event, records) {
    if (event?.extendedProps?.portalGestorBucketPriority !== undefined) {
        return event.extendedProps.portalGestorBucketPriority;
    }
    const record = records[event.id];
    if (!record) {
        return 99;
    }
    return COLOR_PRIORITY[record.colorIndex] ?? 99;
}

patch(CalendarCommonRenderer.prototype, {
    get options() {
        const options = super.options;

        if (this.props.model.resModel !== PORTALGESTOR_RES_MODEL) {
            return options;
        }

        return {
            ...options,
            eventOrderStrict: true,
            eventOrder: (event1, event2) => {
                const priorityDiff =
                    getCalendarPriority(event1, this.props.model.records) -
                    getCalendarPriority(event2, this.props.model.records);

                if (priorityDiff) {
                    return priorityDiff;
                }

                const titleDiff = (event1.title || "").localeCompare(event2.title || "", undefined, {
                    sensitivity: "base",
                });
                if (titleDiff) {
                    return titleDiff;
                }

                return String(event1.id).localeCompare(String(event2.id), undefined, {
                    numeric: true,
                });
            },
        };
    },
});
