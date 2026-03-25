/** @odoo-module **/

import { DateTimePicker } from "@web/core/datetime/datetime_picker";

DateTimePicker.defaultProps = {
    ...DateTimePicker.defaultProps,
    showWeekNumbers: false,
};
