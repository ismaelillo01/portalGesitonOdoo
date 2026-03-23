/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onMounted, onPatched, onWillUnmount, useExternalListener, useState } from "@odoo/owl";

const MIN_EMPTY_ROWS = 4;
const FALLBACK_ROW_HEIGHT = 44;

function getUiBrianMinimumEmptyRows(renderer) {
    let nbEmptyRow = Math.max(0, MIN_EMPTY_ROWS - renderer.props.list.records.length);
    if (nbEmptyRow > 0 && renderer.displayRowCreates) {
        nbEmptyRow -= 1;
    }
    return Math.max(0, nbEmptyRow);
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.uiBrianEmptyRows = useState({ value: getUiBrianMinimumEmptyRows(this) });
        this.uiBrianEmptyRowsFrame = null;
        this.uiBrianScheduleEmptyRowsSync = () => {
            const minimumEmptyRows = getUiBrianMinimumEmptyRows(this);
            if (this.uiBrianEmptyRowsFrame) {
                browser.cancelAnimationFrame(this.uiBrianEmptyRowsFrame);
                this.uiBrianEmptyRowsFrame = null;
            }
            if (this.props.list.isGrouped || this.isX2Many || this.env.inDialog) {
                if (minimumEmptyRows !== this.uiBrianEmptyRows.value) {
                    this.uiBrianEmptyRows.value = minimumEmptyRows;
                }
                return;
            }
            this.uiBrianEmptyRowsFrame = browser.requestAnimationFrame(() => {
                this.uiBrianEmptyRowsFrame = null;
                const nextValue = this.computeUiBrianEmptyRows();
                if (nextValue !== this.uiBrianEmptyRows.value) {
                    this.uiBrianEmptyRows.value = nextValue;
                }
            });
        };
        onMounted(this.uiBrianScheduleEmptyRowsSync);
        onPatched(this.uiBrianScheduleEmptyRowsSync);
        onWillUnmount(() => {
            if (this.uiBrianEmptyRowsFrame) {
                browser.cancelAnimationFrame(this.uiBrianEmptyRowsFrame);
                this.uiBrianEmptyRowsFrame = null;
            }
        });
        useExternalListener(window, "resize", this.uiBrianScheduleEmptyRowsSync);
    },

    computeUiBrianEmptyRows() {
        const nbEmptyRow = getUiBrianMinimumEmptyRows(this);
        if (this.props.list.isGrouped || this.isX2Many || this.env.inDialog) {
            return nbEmptyRow;
        }

        const root = this.rootRef?.el;
        const table = this.tableRef?.el;
        if (!root || !table || this.props.list.isGrouped) {
            return nbEmptyRow;
        }

        const viewport =
            root.closest(".o_content") || root.closest(".o_view_controller") || root.parentElement;
        if (!viewport || viewport === root.parentElement) {
            return nbEmptyRow;
        }
        const viewportRect = viewport?.getBoundingClientRect();
        const tableRect = table.getBoundingClientRect();
        const theadHeight = table.querySelector("thead")?.getBoundingClientRect().height || 0;
        const tfootHeight = table.querySelector("tfoot")?.getBoundingClientRect().height || 0;
        const sampleRow =
            table.querySelector("tbody .o_data_row") ||
            table.querySelector("tbody .o_group_header") ||
            table.querySelector("tbody tr");
        const rowHeight = sampleRow?.getBoundingClientRect().height || FALLBACK_ROW_HEIGHT;
        const availableBodyHeight = Math.max(
            rowHeight,
            (viewportRect?.bottom || browser.innerHeight) - tableRect.top - theadHeight - tfootHeight
        );
        const nonEmptyRowCount = this.props.list.records.length + (this.displayRowCreates ? 1 : 0);
        const targetRowCount = Math.ceil(availableBodyHeight / rowHeight);

        return Math.max(0, Math.max(nbEmptyRow, targetRowCount - nonEmptyRowCount));
    },

    get getEmptyRowIds() {
        return Array.from({ length: Math.max(0, this.uiBrianEmptyRows.value || 0) }, (_, index) => index);
    },
});
