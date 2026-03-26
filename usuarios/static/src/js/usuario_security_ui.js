/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";
import { onWillRender } from "@odoo/owl";

const TARGET_RES_MODEL = "usuarios.usuario";

function isBlockedUserRecord(data) {
    return Boolean(data?.manager_edit_blocked);
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        onWillRender(() => {
            if (this.props.resModel !== TARGET_RES_MODEL) {
                return;
            }
            const { edit } = this.archInfo.activeActions;
            this.canEdit =
                edit && !this.props.preventEdit && !isBlockedUserRecord(this.model?.root?.data);
        });
    },

    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);
        if (this.props.resModel !== TARGET_RES_MODEL || !isBlockedUserRecord(this.model?.root?.data)) {
            return items;
        }
        for (const itemName of ["delete", "duplicate"]) {
            if (items[itemName]) {
                items[itemName] = {
                    ...items[itemName],
                    isAvailable: () => false,
                };
            }
        }
        return items;
    },
});

patch(ListController.prototype, {
    async openRecord(record, force = false) {
        if (this.props.resModel === TARGET_RES_MODEL && isBlockedUserRecord(record?.data)) {
            const dirty = await record.isDirty();
            if (dirty) {
                await record.save();
            }
            const activeIds = this.model.root.records.map((datapoint) => datapoint.resId);
            return this.props.selectRecord(record.resId, { activeIds, force, mode: "readonly" });
        }
        return super.openRecord(record, force);
    },
});
