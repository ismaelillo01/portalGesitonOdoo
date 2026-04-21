/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { CalendarModel } from "@web/views/calendar/calendar_model";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { CalendarFilterPanel } from "@web/views/calendar/filter_panel/calendar_filter_panel";
import { Component, onWillUnmount, useState } from "@odoo/owl";

const { DateTime } = luxon;

const TARGET_RES_MODEL = "portalgestor.asignacion";
const PORTAL_GESTOR_CALENDAR_CHANNEL = "portalgestor.calendar";
const PORTAL_GESTOR_CALENDAR_NOTIFICATION = "portalgestor.calendar.updated";
const PORTAL_GESTOR_REALTIME_DEBOUNCE = 150;
const USER_FILTER_FIELD = "usuario_id";
const WORKER_FILTER_FIELD = "trabajador_calendar_filter_id";
const FILTER_FIELDS = [USER_FILTER_FIELD, WORKER_FILTER_FIELD];
const ONLY_MINE_STORAGE_KEY = `${TARGET_RES_MODEL}.onlyMine`;

const FILTER_CONFIG = {
    [USER_FILTER_FIELD]: {
        model: "usuarios.usuario",
        placeholder: "Buscar usuario",
        domain: [["baja", "=", false], ["has_ap_service", "=", true]],
    },
    [WORKER_FILTER_FIELD]: {
        model: "trabajadores.trabajador",
        placeholder: "Buscar AP",
        domain: [["baja", "=", false]],
    },
};

const USER_OPTION_TEMPLATE = "portalGestor.UserAutocompleteOption";

async function loadPortalGestorUserTypes(orm, userIds) {
    const ids = [...new Set((userIds || []).filter(Boolean))];
    if (!ids.length) {
        return {};
    }
    return orm.call("usuarios.usuario", "get_portalgestor_user_types", [ids]);
}

function getPortalGestorOnlyMineStorageKey() {
    return `${ONLY_MINE_STORAGE_KEY}.${user.userId}`;
}

function getPortalGestorOnlyMineStoredValue() {
    const rawValue = browser.sessionStorage.getItem(getPortalGestorOnlyMineStorageKey());
    return rawValue ? JSON.parse(rawValue) : false;
}

function setPortalGestorOnlyMineStoredValue(value) {
    browser.sessionStorage.setItem(getPortalGestorOnlyMineStorageKey(), JSON.stringify(Boolean(value)));
}

function getPortalGestorOwnerName(rawRecord) {
    const ownerValue = rawRecord?.gestor_owner_id;
    return Array.isArray(ownerValue) ? ownerValue[1] || "" : "";
}

function wrapPortalGestorEventContent(content, ownerName) {
    if (!content?.domNodes?.length || !ownerName) {
        return content;
    }
    const wrapper = document.createElement("div");
    wrapper.className = "o_portalgestor_event_content";
    for (const node of content.domNodes) {
        wrapper.appendChild(node);
    }
    const ownerNode = document.createElement("span");
    ownerNode.className = "o_portalgestor_event_owner";
    ownerNode.textContent = ownerName;
    ownerNode.title = `${_t("Gestor")}: ${ownerName}`;
    wrapper.appendChild(ownerNode);
    return { domNodes: [wrapper] };
}

export class PortalGestorBucketDialog extends Component {
    static template = "portalGestor.CalendarBucketDialog";
    static components = { Dialog };
    static props = {
        bucketDate: String,
        bucketType: String,
        close: Function,
        count: Number,
        formViewId: { type: [Number, Boolean], optional: true },
        label: String,
        portalGestorContext: { type: Object, optional: true },
        records: Array,
        title: String,
    };

    setup() {
        this.orm = useService("orm");
        this.busService = useService("bus_service");
        this.dialogService = useService("dialog");
        this.state = useState({
            count: this.props.count,
            records: [...this.props.records],
        });
        this.portalGestorBusListener = (payload) => {
            if (this.isAffectedByCalendarUpdate(payload)) {
                void this.reloadRecords();
            }
        };
        this.busService.subscribe(PORTAL_GESTOR_CALENDAR_NOTIFICATION, this.portalGestorBusListener);
        onWillUnmount(() => {
            this.busService.unsubscribe(PORTAL_GESTOR_CALENDAR_NOTIFICATION, this.portalGestorBusListener);
        });
    }

    async openRecord(record) {
        this.dialogService.add(FormViewDialog, {
            resModel: TARGET_RES_MODEL,
            resId: record.id,
            viewId: this.props.formViewId || false,
            mode: record.can_edit === false ? "readonly" : "edit",
            title: record.form_title || record.name || _t("Horario"),
        });
        this.props.close();
    }

    isAffectedByCalendarUpdate(payload) {
        const changedDates = payload?.changed_dates || [];
        const bucketTypes = payload?.bucket_types || [];
        return (
            changedDates.includes(this.props.bucketDate) &&
            (!bucketTypes.length || bucketTypes.includes(this.props.bucketType))
        );
    }

    async reloadRecords() {
        const records = await this.orm.call(
            TARGET_RES_MODEL,
            "get_calendar_bucket_records",
            [this.props.bucketDate, this.props.bucketType],
            { context: this.props.portalGestorContext || {} }
        );
        this.state.records = records;
        this.state.count = records.length;
    }
}

function getPortalGestorRecordFilterIds(section) {
    return (
        section?.filters
            ?.filter((filter) => filter.type === "record" && filter.recordId)
            .map((filter) => filter.recordId) || []
    );
}

function getSingleActivePortalGestorFilter(filterSections, targetFields = []) {
    const matches = [];
    for (const fieldName of targetFields) {
        const section = filterSections?.[fieldName];
        for (const filter of section?.filters || []) {
            if (filter.type !== "record" || !filter.active) {
                continue;
            }
            const value = filter.value || filter.recordId;
            if (!value) {
                continue;
            }
            matches.push({ fieldName, value });
        }
    }
    return matches.length === 1 ? matches[0] : null;
}

function hasPortalGestorSearch(section) {
    return (section?.filters || []).some(
        (filter) => filter.type === "record" && filter.active !== false
    );
}

function isPortalGestorSummaryMode(model, data) {
    return (
        model.resModel === TARGET_RES_MODEL &&
        model.scale === "month" &&
        !FILTER_FIELDS.some((fieldName) => hasPortalGestorSearch(data.filterSections[fieldName]))
    );
}

function clonePortalGestorBuckets(buckets = []) {
    return buckets.map((bucket) => ({ ...bucket }));
}

function getPortalGestorRangeKey(startISO, endISO, scopeKey = "all") {
    return `${startISO}|${endISO}|${scopeKey}`;
}

function mergePortalGestorPayload(currentPayload, nextPayload) {
    currentPayload = currentPayload || {};
    nextPayload = nextPayload || {};
    return {
        action_kind: nextPayload.action_kind || currentPayload.action_kind || "write",
        assignment_ids: [...new Set([...(currentPayload.assignment_ids || []), ...(nextPayload.assignment_ids || [])])],
        bucket_types: [...new Set([...(currentPayload.bucket_types || []), ...(nextPayload.bucket_types || [])])],
        changed_dates: [...new Set([...(currentPayload.changed_dates || []), ...(nextPayload.changed_dates || [])])],
    };
}

function doesPortalGestorPayloadIntersectRange(payload, range) {
    const startISO = range?.start?.toISODate();
    const endISO = range?.end?.toISODate();
    return Boolean(
        startISO &&
            endISO &&
            (payload?.changed_dates || []).some((dateValue) => dateValue >= startISO && dateValue <= endISO)
    );
}

function getPortalGestorHolidayWorkerId(filterSections) {
    const activeFilter = getSingleActivePortalGestorFilter(filterSections, FILTER_FIELDS);
    return activeFilter?.fieldName === WORKER_FILTER_FIELD ? activeFilter.value : false;
}

patch(CalendarModel.prototype, {
    setup() {
        super.setup(...arguments);
        this.data.portalGestorBucketEvents = [];
        this.data.portalGestorHolidayMarkers = [];
        this.portalGestorBucketCache = new Map();
        this.portalGestorBucketPendingRequests = new Map();
        this.portalGestorBucketCacheVersion = 0;
        this.portalGestorQueuedRefresh = null;
        this.portalGestorRefreshTimeout = null;
        this.portalGestorSummaryRequestId = 0;
    },

    get portalGestorBucketEvents() {
        return this.data.portalGestorBucketEvents || [];
    },

    get portalGestorHolidayMarkers() {
        return this.data.portalGestorHolidayMarkers || [];
    },

    isPortalGestorOnlyMineEnabled() {
        return Boolean(this.meta.context?.portalgestor_only_my_schedules);
    },

    getPortalGestorOrmContext() {
        return this.isPortalGestorOnlyMineEnabled()
            ? { portalgestor_only_my_schedules: true }
            : {};
    },

    makeContextDefaults(rawRecord) {
        const context = super.makeContextDefaults(...arguments);
        if (this.resModel !== TARGET_RES_MODEL) {
            return context;
        }

        const activeFilter = getSingleActivePortalGestorFilter(
            this.data?.filterSections,
            FILTER_FIELDS
        );
        if (!activeFilter) {
            return context;
        }

        if (activeFilter.fieldName === USER_FILTER_FIELD) {
            context.default_usuario_id = activeFilter.value;
        } else if (activeFilter.fieldName === WORKER_FILTER_FIELD && !context.default_lineas_ids) {
            context.default_lineas_ids = [[0, 0, { trabajador_id: activeFilter.value }]];
        }
        return context;
    },

    isPortalGestorSummaryMode(data = this.data) {
        return isPortalGestorSummaryMode(this, data);
    },

    getPortalGestorMonthRange(anchorDate) {
        let start = anchorDate.startOf("month");
        const currentWeekOffset = (start.weekday - this.firstDayOfWeek + 7) % 7;
        start = start.minus({ days: currentWeekOffset }).startOf("day");
        const end = start.plus({ weeks: 6, days: -1 }).endOf("day");
        return { start, end };
    },

    getPortalGestorAdjacentSummaryRanges() {
        const monthDate = this.meta.date.startOf("month");
        return [
            this.getPortalGestorMonthRange(monthDate.minus({ months: 1 })),
            this.getPortalGestorMonthRange(monthDate.plus({ months: 1 })),
        ];
    },

    invalidatePortalGestorSummaryCache(changedDates = []) {
        this.portalGestorBucketCacheVersion += 1;
        if (!changedDates.length) {
            this.portalGestorBucketCache.clear();
            return;
        }
        for (const [key, entry] of this.portalGestorBucketCache.entries()) {
            const intersects = changedDates.some(
                (dateValue) => dateValue >= entry.startISO && dateValue <= entry.endISO
            );
            if (intersects) {
                this.portalGestorBucketCache.delete(key);
            }
        }
    },

    async loadPortalGestorBucketSummary(startISO, endISO, { force = false } = {}) {
        const key = getPortalGestorRangeKey(
            startISO,
            endISO,
            this.isPortalGestorOnlyMineEnabled() ? `mine:${user.userId}` : "all"
        );
        if (force) {
            this.portalGestorBucketCache.delete(key);
        }
        if (!force && this.portalGestorBucketCache.has(key)) {
            return clonePortalGestorBuckets(this.portalGestorBucketCache.get(key).buckets);
        }
        if (!force && this.portalGestorBucketPendingRequests.has(key)) {
            return clonePortalGestorBuckets(await this.portalGestorBucketPendingRequests.get(key));
        }

        const cacheVersion = this.portalGestorBucketCacheVersion;
        const request = this.orm
            .call(this.resModel, "get_calendar_bucket_summary", [startISO, endISO], {
                context: this.getPortalGestorOrmContext(),
            })
            .then((buckets) => {
                const normalizedBuckets = clonePortalGestorBuckets(buckets);
                if (cacheVersion === this.portalGestorBucketCacheVersion) {
                    this.portalGestorBucketCache.set(key, {
                        buckets: normalizedBuckets,
                        endISO,
                        startISO,
                    });
                }
                return normalizedBuckets;
            })
            .finally(() => {
                if (this.portalGestorBucketPendingRequests.get(key) === request) {
                    this.portalGestorBucketPendingRequests.delete(key);
                }
            });
        this.portalGestorBucketPendingRequests.set(key, request);
        return clonePortalGestorBuckets(await request);
    },

    prefetchPortalGestorAdjacentRanges() {
        if (this.resModel !== TARGET_RES_MODEL || this.scale !== "month") {
            return;
        }
        const promises = this.getPortalGestorAdjacentSummaryRanges().map((range) =>
            this.loadPortalGestorBucketSummary(range.start.toISODate(), range.end.toISODate()).catch(() => [])
        );
        void Promise.allSettled(promises);
    },

    async loadPortalGestorHolidayMarkers(startISO, endISO, workerId = false) {
        if (this.resModel !== TARGET_RES_MODEL) {
            return [];
        }
        return this.orm.call(
            this.resModel,
            "get_calendar_holiday_markers",
            [startISO, endISO, workerId || false],
            { context: this.getPortalGestorOrmContext() }
        );
    },

    computeDomain(data) {
        const domain = super.computeDomain(...arguments);
        if (this.resModel !== TARGET_RES_MODEL || !this.isPortalGestorOnlyMineEnabled()) {
            return domain;
        }
        return [...domain, ["gestor_owner_id", "=", user.userId]];
    },

    fetchRecords(data) {
        if (this.resModel !== TARGET_RES_MODEL) {
            return super.fetchRecords(...arguments);
        }
        const { fieldNames, resModel } = this.meta;
        return this.orm.searchRead(
            resModel,
            this.computeDomain(data),
            [...new Set([...fieldNames, ...Object.keys(this.meta.activeFields)])],
            { context: this.getPortalGestorOrmContext() }
        );
    },

    queuePortalGestorRealtimeRefresh(payload) {
        if (this.resModel !== TARGET_RES_MODEL) {
            return;
        }
        if (!payload) {
            return;
        }

        this.invalidatePortalGestorSummaryCache(payload?.changed_dates || []);
        if (!doesPortalGestorPayloadIntersectRange(payload, this.data.range)) {
            return;
        }

        this.portalGestorQueuedRefresh = mergePortalGestorPayload(this.portalGestorQueuedRefresh, payload);
        browser.clearTimeout(this.portalGestorRefreshTimeout);
        this.portalGestorRefreshTimeout = browser.setTimeout(() => {
            const nextPayload = this.portalGestorQueuedRefresh || {};
            this.portalGestorQueuedRefresh = null;
            this.portalGestorRefreshTimeout = null;
            void this.refreshPortalGestorVisibleData(nextPayload);
        }, PORTAL_GESTOR_REALTIME_DEBOUNCE);
    },

    async refreshPortalGestorVisibleData(payload = {}) {
        if (!doesPortalGestorPayloadIntersectRange(payload, this.data.range)) {
            return;
        }

        if (!this.isPortalGestorSummaryMode(this.data)) {
            await this.load();
            return;
        }

        const startISO = this.data.range.start.toISODate();
        const endISO = this.data.range.end.toISODate();
        const requestId = ++this.portalGestorSummaryRequestId;
        const buckets = await this.loadPortalGestorBucketSummary(startISO, endISO, { force: true });
        const holidayMarkers = await this.loadPortalGestorHolidayMarkers(startISO, endISO);
        if (requestId !== this.portalGestorSummaryRequestId) {
            return;
        }
        if (
            !this.data.range ||
            this.data.range.start.toISODate() !== startISO ||
            this.data.range.end.toISODate() !== endISO ||
            !this.isPortalGestorSummaryMode(this.data)
        ) {
            return;
        }
        this.data.portalGestorBucketEvents = buckets;
        this.data.portalGestorHolidayMarkers = holidayMarkers;
        this.notify();
        this.prefetchPortalGestorAdjacentRanges();
    },

    async updateData(data) {
        if (this.resModel !== TARGET_RES_MODEL) {
            return super.updateData(...arguments);
        }

        data.range = this.computeRange();
        if (this.meta.showUnusualDays) {
            data.unusualDays = await this.loadUnusualDays(data);
        }

        const { sections, dynamicFiltersInfo } = await this.loadFilters(data);
        data.filterSections = sections;

        if (this.isPortalGestorSummaryMode(data)) {
            data.records = {};
            data.portalGestorBucketEvents = await this.loadPortalGestorBucketSummary(
                data.range.start.toISODate(),
                data.range.end.toISODate()
            );
            data.portalGestorHolidayMarkers = await this.loadPortalGestorHolidayMarkers(
                data.range.start.toISODate(),
                data.range.end.toISODate(),
                false
            );
            this.prefetchPortalGestorAdjacentRanges();
            return;
        }

        data.portalGestorBucketEvents = [];
        data.portalGestorHolidayMarkers = await this.loadPortalGestorHolidayMarkers(
            data.range.start.toISODate(),
            data.range.end.toISODate(),
            getPortalGestorHolidayWorkerId(data.filterSections)
        );
        data.records = await this.loadRecords(data);
        const dynamicSections = await this.loadDynamicFilters(data, dynamicFiltersInfo);
        Object.assign(data.filterSections, dynamicSections);

        for (const [recordId, record] of Object.entries(data.records)) {
            for (const [fieldName, filterInfo] of Object.entries(dynamicSections)) {
                for (const filter of filterInfo.filters) {
                    const rawValue = record.rawRecord[fieldName];
                    const value = Array.isArray(rawValue) ? rawValue[0] : rawValue;
                    if (filter.value === value && !filter.active) {
                        delete data.records[recordId];
                    }
                }
            }
        }
    },

    async createFilter(fieldName, filterValue) {
        if (this.resModel !== TARGET_RES_MODEL || !FILTER_FIELDS.includes(fieldName)) {
            return super.createFilter(...arguments);
        }

        const info = this.meta.filtersInfo[fieldName];
        if (!info?.writeFieldName || !info.writeResModel) {
            return;
        }

        const selectedValues = Array.isArray(filterValue) ? filterValue.filter(Boolean) : [filterValue];
        const selectedValue = selectedValues[selectedValues.length - 1];

        for (const targetFieldName of FILTER_FIELDS) {
            const section = this.data.filterSections[targetFieldName];
            const targetInfo = this.meta.filtersInfo[targetFieldName];
            const recordIds = getPortalGestorRecordFilterIds(section);
            if (recordIds.length && targetInfo?.writeResModel) {
                await this.orm.unlink(targetInfo.writeResModel, recordIds);
            }
        }

        if (!selectedValue) {
            await this.load();
            return;
        }

        const data = {
            user_id: user.userId,
            [info.writeFieldName]: selectedValue,
        };
        if (info.filterFieldName) {
            data[info.filterFieldName] = true;
        }
        await this.orm.create(info.writeResModel, [data]);
        await this.load();
    },

    async loadFilterSection(fieldName, filterInfo, previousSection) {
        const section = await super.loadFilterSection(...arguments);
        if (this.resModel !== TARGET_RES_MODEL || !FILTER_FIELDS.includes(fieldName) || !section) {
            return section;
        }

        const recordFilters = section.filters.filter((filter) => filter.type === "record");
        const allFilter = section.filters.find((filter) => filter.type === "all");
        if (allFilter) {
            allFilter.active = !recordFilters.some((filter) => filter.active);
        }
        return section;
    },
});

patch(CalendarController.prototype, {
    setup() {
        super.setup(...arguments);
        this.portalGestorOnlyMineState = useState({
            onlyMine: this.props.resModel === TARGET_RES_MODEL ? getPortalGestorOnlyMineStoredValue() : false,
        });
    },

    onWillStartModel() {
        super.onWillStartModel(...arguments);
        if (this.props.resModel !== TARGET_RES_MODEL) {
            return;
        }
        this.model.meta.context = {
            ...(this.model.meta.context || {}),
            portalgestor_only_my_schedules: this.portalGestorOnlyMineState.onlyMine,
        };
    },

    get showPortalGestorOnlyMineToggle() {
        return this.props.resModel === TARGET_RES_MODEL;
    },

    async togglePortalGestorOnlyMine() {
        if (!this.showPortalGestorOnlyMineToggle) {
            return;
        }
        const nextValue = !this.portalGestorOnlyMineState.onlyMine;
        this.portalGestorOnlyMineState.onlyMine = nextValue;
        setPortalGestorOnlyMineStoredValue(nextValue);
        await this.model.load({
            context: {
                ...(this.model.meta.context || {}),
                portalgestor_only_my_schedules: nextValue,
            },
        });
    },
});

patch(CalendarCommonRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.addDialog = useOwnedDialogs();
        this.orm = useService("orm");
        this.busService = useService("bus_service");
        if (this.props.model.resModel === TARGET_RES_MODEL) {
            this.portalGestorBusListener = (payload) => {
                this.props.model.queuePortalGestorRealtimeRefresh(payload);
            };
            this.busService.subscribe(PORTAL_GESTOR_CALENDAR_NOTIFICATION, this.portalGestorBusListener);
            void this.busService.addChannel(PORTAL_GESTOR_CALENDAR_CHANNEL);
            onWillUnmount(() => {
                this.busService.unsubscribe(PORTAL_GESTOR_CALENDAR_NOTIFICATION, this.portalGestorBusListener);
                this.busService.deleteChannel(PORTAL_GESTOR_CALENDAR_CHANNEL);
            });
        }
    },

    get options() {
        const options = super.options;
        if (this.props.model.resModel !== TARGET_RES_MODEL) {
            return options;
        }

        const originalEvents = options.events?.bind(this);
        const originalEventClick = options.eventClick?.bind(this);
        const originalEventContent = options.eventContent?.bind(this);
        return {
            ...options,
            events: (fetchInfo, successCb, failureCb) => {
                if (this.props.model.isPortalGestorSummaryMode()) {
                    successCb([
                        ...this.mapPortalGestorHolidayMarkersToEvents(),
                        ...this.mapPortalGestorBucketsToEvents(),
                    ]);
                    return;
                }

                if (!originalEvents) {
                    successCb([
                        ...this.mapRecordsToEvents(),
                        ...this.mapPortalGestorHolidayMarkersToEvents(),
                    ]);
                    return;
                }
                return originalEvents(
                    fetchInfo,
                    (events) => successCb([...events, ...this.mapPortalGestorHolidayMarkersToEvents()]),
                    failureCb
                );
            },
            eventClick: (info) => {
                if (info.event.extendedProps?.isPortalGestorBucket) {
                    info.jsEvent?.preventDefault();
                    this.openPortalGestorBucket(info.event.extendedProps);
                    return;
                }
                if (info.event.extendedProps?.isPortalGestorHolidayMarker) {
                    info.jsEvent?.preventDefault();
                    return;
                }
                return originalEventClick?.(info);
            },
            eventContent: (arg) => {
                if (arg.event.extendedProps?.isPortalGestorBucket) {
                    const title = document.createElement("div");
                    title.className = "o_event_title";
                    title.textContent = arg.event.title || "";
                    return { domNodes: [title] };
                }
                const content = originalEventContent?.(arg);
                const record = this.props.model.records[arg.event.id];
                if (!record?.isMonth) {
                    return content;
                }
                return wrapPortalGestorEventContent(
                    content,
                    getPortalGestorOwnerName(record.rawRecord)
                );
            },
        };
    },

    mapPortalGestorHolidayMarkersToEvents() {
        return this.props.model.portalGestorHolidayMarkers.map((marker) => {
            const start = DateTime.fromISO(marker.date);
            return {
                id: marker.id,
                title: marker.label,
                start: start.toISODate(),
                end: start.plus({ days: 1 }).toISODate(),
                allDay: true,
                display: "background",
                editable: false,
                startEditable: false,
                durationEditable: false,
                overlap: true,
                classNames: ["o_portalgestor_holiday_marker", `o_portalgestor_holiday_marker--${marker.marker_type}`],
                extendedProps: {
                    isPortalGestorHolidayMarker: true,
                    portalGestorHolidayNames: marker.names || "",
                    portalGestorHolidayType: marker.marker_type,
                },
            };
        });
    },

    mapPortalGestorBucketsToEvents() {
        return this.props.model.portalGestorBucketEvents.map((bucket) => {
            const start = DateTime.fromISO(bucket.date);
            return {
                id: bucket.id,
                title: bucket.title,
                start: start.toISODate(),
                end: start.plus({ days: 1 }).toISODate(),
                allDay: true,
                editable: false,
                startEditable: false,
                durationEditable: false,
                extendedProps: {
                    isPortalGestorBucket: true,
                    portalGestorBucketCount: bucket.count,
                    portalGestorBucketDate: bucket.date,
                    portalGestorBucketLabel: bucket.label,
                    portalGestorBucketPriority: bucket.priority,
                    portalGestorBucketType: bucket.bucket_type,
                },
            };
        });
    },

    async openPortalGestorBucket(bucket) {
        const records = await this.orm.call(
            TARGET_RES_MODEL,
            "get_calendar_bucket_records",
            [bucket.portalGestorBucketDate, bucket.portalGestorBucketType],
            { context: this.props.model.getPortalGestorOrmContext() }
        );

        this.addDialog(PortalGestorBucketDialog, {
            bucketDate: bucket.portalGestorBucketDate,
            title: DateTime.fromISO(bucket.portalGestorBucketDate).toLocaleString(DateTime.DATE_FULL),
            label: bucket.portalGestorBucketLabel,
            count: bucket.portalGestorBucketCount,
            bucketType: bucket.portalGestorBucketType,
            formViewId: this.props.model.formViewId,
            portalGestorContext: this.props.model.getPortalGestorOrmContext(),
            records,
        });
    },

    eventClassNames(arg) {
        const classes = super.eventClassNames(...arguments);
        if (arg.event.extendedProps?.isPortalGestorBucket) {
            classes.push("o_portalgestor_bucket");
            classes.push(`o_portalgestor_bucket--${arg.event.extendedProps.portalGestorBucketType}`);
        }
        if (arg.event.extendedProps?.isPortalGestorHolidayMarker) {
            classes.push("o_portalgestor_holiday_marker");
            classes.push(`o_portalgestor_holiday_marker--${arg.event.extendedProps.portalGestorHolidayType}`);
        }
        return classes;
    },
});

patch(CalendarFilterPanel.prototype, {
    getAutoCompleteProps(section) {
        const props = super.getAutoCompleteProps(...arguments);
        if (this.props.model.resModel !== TARGET_RES_MODEL || !FILTER_FIELDS.includes(section.fieldName)) {
            return props;
        }

        return {
            ...props,
            placeholder: FILTER_CONFIG[section.fieldName].placeholder,
            sources: props.sources?.map((source) =>
                section.fieldName === USER_FILTER_FIELD
                    ? { ...source, optionTemplate: USER_OPTION_TEMPLATE }
                    : source
            ),
        };
    },

    async loadSource(section, request) {
        if (this.props.model.resModel !== TARGET_RES_MODEL || !FILTER_FIELDS.includes(section.fieldName)) {
            return super.loadSource(...arguments);
        }

        const config = FILTER_CONFIG[section.fieldName];
        const excludedIds = section.filters
            .filter((filter) => filter.type === "record")
            .map((filter) => filter.value);
        const domain = [...config.domain, ["id", "not in", excludedIds]];
        const records = await this.orm.call(config.model, "name_search", [], {
            name: request,
            operator: "ilike",
            args: domain,
            limit: 8,
            context: {},
        });

        const userTypes =
            section.fieldName === USER_FILTER_FIELD
                ? await loadPortalGestorUserTypes(
                      this.orm,
                      records.map((result) => result[0])
                  )
                : {};
        const options = records.map((result) => ({
            value: result[0],
            label: result[1],
            model: config.model,
            resModel: config.model,
            portalGestorUserTypeBadge: userTypes[result[0]]?.badge || "",
            portalGestorUserTypeLabel: userTypes[result[0]]?.label || "",
        }));

        if (records.length > 7) {
            options.push({
                label: _t("Search More..."),
                action: () => this.onSearchMore(section, config.model, domain, request),
                classList: "o_calendar_dropdown_option",
            });
        }

        if (!records.length) {
            options.push({
                label: _t("No records"),
                classList: "o_m2o_no_result",
                unselectable: true,
            });
        }

        return options;
    },
});
