# -*- coding: utf-8 -*-
import calendar
import json
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models, Command
from odoo.exceptions import ValidationError
from odoo.tools import create_index


MONTH_SELECTION = [
    ('1', 'Enero'),
    ('2', 'Febrero'),
    ('3', 'Marzo'),
    ('4', 'Abril'),
    ('5', 'Mayo'),
    ('6', 'Junio'),
    ('7', 'Julio'),
    ('8', 'Agosto'),
    ('9', 'Septiembre'),
    ('10', 'Octubre'),
    ('11', 'Noviembre'),
    ('12', 'Diciembre'),
]

MONTH_LABELS = dict(MONTH_SELECTION)
WEEKDAY_LABELS = {
    0: 'Lun',
    1: 'Mar',
    2: 'Mie',
    3: 'Jue',
    4: 'Vie',
    5: 'Sab',
    6: 'Dom',
}


class AsignacionMensual(models.Model):
    _inherit = 'portalgestor.asignacion.mensual'

    schedule_type = fields.Selection(
        selection=[
            ('legacy', 'Legacy'),
            ('monthly_template', 'Plantilla mensual'),
        ],
        string='Tipo de trabajo fijo',
        default='monthly_template',
        required=True,
        index=True,
        copy=False,
    )
    month = fields.Selection(
        selection=MONTH_SELECTION,
        string='Mes',
        default=lambda self: str(fields.Date.context_today(self).month),
        index=True,
    )
    year = fields.Integer(
        string='Ano',
        default=lambda self: fields.Date.context_today(self).year,
        index=True,
    )
    template_month_label = fields.Char(
        string='Mes',
        compute='_compute_template_month_label',
    )
    template_week_ids = fields.One2many(
        'portalgestor.asignacion.mensual.semana',
        'asignacion_mensual_id',
        string='Semanas',
        copy=False,
    )
    template_day_ids = fields.One2many(
        'portalgestor.asignacion.mensual.dia',
        'asignacion_mensual_id',
        string='Dias de plantilla',
        copy=False,
    )
    template_day_line_ids = fields.One2many(
        'portalgestor.asignacion.mensual.dia.linea',
        'asignacion_mensual_id',
        string='Tramos de plantilla',
        copy=False,
    )
    template_week_count = fields.Integer(
        string='Semanas del mes',
        compute='_compute_template_counts',
    )
    template_day_count = fields.Integer(
        string='Dias con horario',
        compute='_compute_template_counts',
    )
    template_line_count = fields.Integer(
        string='Tramos en plantilla',
        compute='_compute_template_counts',
    )
    template_header_locked = fields.Boolean(
        string='Cabecera bloqueada',
        compute='_compute_template_locks',
    )
    template_content_locked = fields.Boolean(
        string='Plantilla bloqueada',
        compute='_compute_template_locks',
    )

    def init(self):
        super().init()
        self.env.cr.execute(
            f"""
                UPDATE {self._table}
                   SET schedule_type = 'legacy'
                 WHERE schedule_type IS NULL
            """
        )

    @staticmethod
    def _get_month_bounds(month_value, year_value):
        month_number = int(month_value)
        year_number = int(year_value)
        month_start = fields.Date.to_date(f"{year_number:04d}-{month_number:02d}-01")
        month_end = month_start + timedelta(days=calendar.monthrange(year_number, month_number)[1] - 1)
        return month_start, month_end

    @classmethod
    def _build_virtual_template_week_commands(cls, month_value, year_value):
        month_number = int(month_value)
        year_number = int(year_value)
        commands = []
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year_number, month_number)
        for sequence, week_dates in enumerate(weeks, start=1):
            month_dates = [week_date for week_date in week_dates if week_date.month == month_number]
            if not month_dates:
                continue
            commands.append(Command.create({
                'sequence': sequence,
                'fecha_inicio': month_dates[0],
                'fecha_fin': month_dates[-1],
                'template_day_ids': [
                    Command.create({
                        'fecha': week_date,
                    })
                    for week_date in month_dates
                ],
            }))
        return commands

    @api.depends('schedule_type', 'month', 'year')
    def _compute_template_month_label(self):
        for record in self:
            if record.schedule_type != 'monthly_template' or not record.month:
                record.template_month_label = ''
                continue
            record.template_month_label = MONTH_LABELS.get(record.month, '')

    @api.depends(
        'schedule_type',
        'template_week_ids',
        'template_day_ids.template_day_line_ids',
        'template_day_ids.template_day_line_ids.trabajador_id',
    )
    def _compute_template_counts(self):
        for record in self:
            if record.schedule_type != 'monthly_template':
                record.template_week_count = 0
                record.template_day_count = 0
                record.template_line_count = 0
                continue
            record.template_week_count = len(record.template_week_ids)
            day_ids_with_lines = {
                day.id
                for day in record.template_day_ids
                if day.template_day_line_ids
            }
            record.template_day_count = len(day_ids_with_lines)
            record.template_line_count = len(record.template_day_line_ids)

    @api.depends('schedule_type', 'confirmado', 'edit_session_pending', 'manager_edit_blocked')
    def _compute_template_locks(self):
        for record in self:
            if record.schedule_type != 'monthly_template':
                record.template_header_locked = False
                record.template_content_locked = False
                continue
            record.template_header_locked = bool(record.manager_edit_blocked or record.confirmado)
            record.template_content_locked = bool(
                record.manager_edit_blocked or (record.confirmado and not record.edit_session_pending)
            )

    @staticmethod
    def _format_hora(hour_float):
        return '%02d:%02d' % (int(hour_float), int((hour_float % 1) * 60))

    @api.depends(
        'schedule_type',
        'usuario_id.name',
        'usuario_id.display_name',
        'fecha_inicio',
        'fecha_fin',
        'linea_fija_ids',
        'template_day_line_ids',
        'month',
        'year',
    )
    def _compute_name(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        super(AsignacionMensual, legacy_records)._compute_name()
        for record in self - legacy_records:
            if not record.usuario_id or not record.month or not record.year:
                record.name = _('Nueva Plantilla Mensual')
                continue
            record.name = _('%(usuario)s | %(mes)s %(ano)s (%(tramos)s tramos)') % {
                'usuario': record.usuario_id.display_name or record.usuario_id.name,
                'mes': MONTH_LABELS.get(record.month, ''),
                'ano': record.year,
                'tramos': len(record.template_day_line_ids),
            }

    @api.constrains('fecha_inicio', 'fecha_fin', 'schedule_type')
    def _check_date_range(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        super(AsignacionMensual, legacy_records)._check_date_range()

    @api.constrains('linea_fija_ids', 'schedule_type', 'template_day_line_ids')
    def _check_lineas_fijas(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        super(AsignacionMensual, legacy_records)._check_lineas_fijas()

    @api.constrains('schedule_type', 'month', 'year', 'usuario_id')
    def _check_monthly_template_identity(self):
        for record in self.filtered(lambda item: item.schedule_type == 'monthly_template'):
            if not record.month or not record.year:
                raise ValidationError(_("Debes indicar un mes y un ano para la plantilla mensual."))
            if record.year < 2000 or record.year > 2100:
                raise ValidationError(_("El ano de la plantilla mensual debe estar entre 2000 y 2100."))
            duplicates = self.search([
                ('id', '!=', record.id),
                ('schedule_type', '=', 'monthly_template'),
                ('usuario_id', '=', record.usuario_id.id),
                ('month', '=', record.month),
                ('year', '=', record.year),
            ], limit=1)
            if duplicates:
                raise ValidationError(
                    _("Ya existe una plantilla mensual para este usuario en %(mes)s/%(ano)s.")
                    % {
                        'mes': record.month,
                        'ano': record.year,
                    }
                )

    def _prepare_template_month_vals(self, vals):
        values = dict(vals)
        if values.get('schedule_type') == 'monthly_template':
            values.setdefault('month', str(fields.Date.context_today(self).month))
            values.setdefault('year', fields.Date.context_today(self).year)
            if values.get('month') and values.get('year'):
                month_start, month_end = self._get_month_bounds(values['month'], values['year'])
                values['fecha_inicio'] = month_start
                values['fecha_fin'] = month_end
        return values

    @staticmethod
    def _is_legacy_vals(vals):
        return any(key in vals for key in ('linea_fija_ids',)) or (
            vals.get('fecha_inicio') and vals.get('fecha_fin') and 'month' not in vals and 'year' not in vals
        )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        schedule_type = (
            values.get('schedule_type')
            or self.env.context.get('default_schedule_type')
            or 'monthly_template'
        )
        if schedule_type != 'monthly_template':
            return values

        today = fields.Date.context_today(self)
        month_value = str(values.get('month') or today.month)
        year_value = int(values.get('year') or today.year)
        month_start, month_end = self._get_month_bounds(month_value, year_value)
        values.setdefault('schedule_type', 'monthly_template')
        values.setdefault('month', month_value)
        values.setdefault('year', year_value)
        values.setdefault('fecha_inicio', month_start)
        values.setdefault('fecha_fin', month_end)
        if not values.get('template_week_ids'):
            values['template_week_ids'] = self._build_virtual_template_week_commands(month_value, year_value)
        return values

    @api.onchange('schedule_type', 'month', 'year')
    def _onchange_template_period(self):
        for record in self:
            if record.schedule_type != 'monthly_template' or not record.month or not record.year:
                continue
            month_start, month_end = self._get_month_bounds(record.month, record.year)
            record.fecha_inicio = month_start
            record.fecha_fin = month_end
            record.template_week_ids = [Command.clear(), *self._build_virtual_template_week_commands(record.month, record.year)]

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            values = dict(vals)
            if not values.get('schedule_type'):
                values['schedule_type'] = 'legacy' if self._is_legacy_vals(values) else 'monthly_template'
            prepared_vals_list.append(self._prepare_template_month_vals(values))

        records = super().create(prepared_vals_list)
        template_records = records.filtered(lambda record: record.schedule_type == 'monthly_template')
        if template_records:
            template_records._ensure_monthly_template_structure(force_rebuild=True)
        return records

    def write(self, vals):
        values = self._prepare_template_month_vals(vals)
        result = super().write(values)
        template_records = self.filtered(lambda record: record.schedule_type == 'monthly_template')
        if template_records and {'month', 'year'} & set(values):
            template_records._ensure_monthly_template_structure(force_rebuild=True)
        return result

    def _sync_generated_assignments(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        if legacy_records:
            return super(AsignacionMensual, legacy_records)._sync_generated_assignments()
        return True

    def _cleanup_invalid_drafts(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        removed_records = super(AsignacionMensual, legacy_records)._cleanup_invalid_drafts()
        monthly_records = self.filtered(lambda record: record.schedule_type == 'monthly_template')
        empty_drafts = monthly_records.filtered(
            lambda record: not record.confirmado
            and not record.edit_session_pending
            and not record.template_day_line_ids
        )
        if empty_drafts:
            empty_drafts.unlink()
        return removed_records | empty_drafts

    def _get_edit_snapshot_payload(self):
        self.ensure_one()
        if self.schedule_type != 'monthly_template':
            return super()._get_edit_snapshot_payload()
        return {
            'schedule_type': self.schedule_type,
            'confirmado': bool(self.confirmado),
            'usuario_id': self.usuario_id.id or False,
            'month': self.month,
            'year': self.year,
            'days': [
                {
                    'fecha': fields.Date.to_string(day.fecha),
                    'selected_for_seed': bool(day.selected_for_seed),
                    'lines': [
                        {
                            'hora_inicio': line.hora_inicio,
                            'hora_fin': line.hora_fin,
                            'trabajador_id': line.trabajador_id.id,
                        }
                        for line in day.template_day_line_ids.sorted(
                            key=lambda item: (item.hora_inicio, item.hora_fin, item.id)
                        )
                    ],
                }
                for day in self.template_day_ids.sorted(key=lambda item: (item.fecha, item.id))
            ],
        }

    def _set_edit_snapshot(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        if legacy_records:
            super(AsignacionMensual, legacy_records)._set_edit_snapshot()
        for record in self.filtered(lambda item: item.schedule_type == 'monthly_template'):
            if record.edit_session_pending:
                continue
            record.write({
                'edit_session_pending': True,
                'edit_snapshot_data': json.dumps(record._get_edit_snapshot_payload()),
            })

    def _restore_edit_snapshot(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        if legacy_records:
            super(AsignacionMensual, legacy_records)._restore_edit_snapshot()
        DayLine = self.env['portalgestor.asignacion.mensual.dia.linea']
        for record in self.filtered(
            lambda item: item.schedule_type == 'monthly_template'
            and item.edit_session_pending
            and item.edit_snapshot_data
        ):
            snapshot = json.loads(record.edit_snapshot_data)
            restore_context = dict(self.env.context, portalgestor_skip_seed_propagation=True)
            record.write({
                'usuario_id': snapshot.get('usuario_id') or False,
                'month': snapshot.get('month'),
                'year': snapshot.get('year'),
                'confirmado': bool(snapshot.get('confirmado', True)),
                'edit_session_pending': False,
                'edit_snapshot_data': False,
            })
            record._ensure_monthly_template_structure(force_rebuild=True)
            day_map = {
                fields.Date.to_string(day.fecha): day
                for day in record.template_day_ids
                if day.fecha
            }
            record.template_day_line_ids.with_context(**restore_context).unlink()
            for day_data in snapshot.get('days', []):
                day = day_map.get(day_data.get('fecha'))
                if not day:
                    continue
                day.with_context(**restore_context).write({
                    'selected_for_seed': bool(day_data.get('selected_for_seed')),
                    'seed_source_day_id': False,
                    'seed_is_pristine': False,
                })
                if day_data.get('lines'):
                    DayLine.with_context(**restore_context).create([
                        {
                            'template_day_id': day.id,
                            'hora_inicio': line_data['hora_inicio'],
                            'hora_fin': line_data['hora_fin'],
                            'trabajador_id': line_data['trabajador_id'],
                        }
                        for line_data in day_data['lines']
                    ])
        return True

    def action_descartar_edicion(self):
        monthly_records = self.filtered(lambda record: record.schedule_type == 'monthly_template')
        legacy_records = self - monthly_records
        if legacy_records:
            super(AsignacionMensual, legacy_records).action_descartar_edicion()
        if monthly_records:
            monthly_records._ensure_current_user_can_manage_users(monthly_records.mapped('usuario_id'))
            monthly_records._restore_edit_snapshot()
        return True

    def action_eliminar_borrador_no_verificado(self):
        monthly_records = self.filtered(lambda record: record.schedule_type == 'monthly_template')
        legacy_records = self - monthly_records
        if legacy_records:
            super(AsignacionMensual, legacy_records).action_eliminar_borrador_no_verificado()
        for record in monthly_records:
            record._ensure_current_user_can_manage_users(record.mapped('usuario_id'))
            if not record.confirmado and not record.edit_session_pending and not record.template_day_line_ids:
                record.unlink()
        return True

    def action_editar(self):
        monthly_records = self.filtered(lambda record: record.schedule_type == 'monthly_template')
        legacy_records = self - monthly_records
        if legacy_records:
            super(AsignacionMensual, legacy_records).action_editar()
        for record in monthly_records:
            record._ensure_current_user_can_manage_users(record.mapped('usuario_id'))
            if record.confirmado and not record.edit_session_pending:
                record._set_edit_snapshot()
        return True

    def name_get(self):
        legacy_records = self.filtered(lambda record: record.schedule_type != 'monthly_template')
        monthly_records = self - legacy_records
        result = []
        if legacy_records:
            result.extend(super(AsignacionMensual, legacy_records).name_get())
        if monthly_records:
            user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
                monthly_records.mapped('usuario_id').ids
            )
            for record in monthly_records:
                result.append((
                    record.id,
                    _('%(usuario)s | %(mes)s %(ano)s (%(tramos)s tramos)') % {
                        'usuario': user_view_data.get(record.usuario_id.id, {}).get('display_name')
                        or record.usuario_id.display_name
                        or record.usuario_id.name,
                        'mes': MONTH_LABELS.get(record.month, ''),
                        'ano': record.year,
                        'tramos': len(record.template_day_line_ids),
                    },
                ))
        return result

    def unlink(self):
        monthly_records = self.filtered(lambda record: record.schedule_type == 'monthly_template')
        legacy_records = self - monthly_records
        if legacy_records:
            super(AsignacionMensual, legacy_records).unlink()
        if monthly_records:
            monthly_records._ensure_current_user_can_manage_users(monthly_records.mapped('usuario_id'))
            touched_assignments = monthly_records.mapped('asignacion_linea_ids.asignacion_id')
            monthly_records.mapped('asignacion_linea_ids').with_context(
                portalgestor_skip_fixed_sync=True,
                portalgestor_skip_fixed_exception=True,
            ).unlink()
            touched_assignments.cleanup_empty_assignments()
            return models.Model.unlink(monthly_records)
        return True

    def _ensure_monthly_template_structure(self, force_rebuild=False):
        Week = self.env['portalgestor.asignacion.mensual.semana']
        Day = self.env['portalgestor.asignacion.mensual.dia']
        for record in self.filtered(lambda item: item.schedule_type == 'monthly_template' and item.month and item.year):
            month_start, month_end = self._get_month_bounds(record.month, record.year)
            if not force_rebuild and record.template_week_ids and record.fecha_inicio == month_start and record.fecha_fin == month_end:
                continue

            preserved_payload = {}
            if force_rebuild:
                preserved_payload = {
                    fields.Date.to_string(day.fecha): {
                        'selected_for_seed': day.selected_for_seed,
                        'lines': [
                            {
                                'hora_inicio': line.hora_inicio,
                                'hora_fin': line.hora_fin,
                                'trabajador_id': line.trabajador_id.id,
                            }
                            for line in day.template_day_line_ids.sorted(
                                key=lambda item: (item.hora_inicio, item.hora_fin, item.id)
                            )
                        ],
                    }
                    for day in record.template_day_ids
                    if day.fecha
                }
                record.template_day_line_ids.with_context(portalgestor_skip_seed_propagation=True).unlink()
                record.template_week_ids.unlink()

            record.with_context(portalgestor_skip_fixed_sync=True).write({
                'fecha_inicio': month_start,
                'fecha_fin': month_end,
            })

            weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(record.year, int(record.month))
            for sequence, week_dates in enumerate(weeks, start=1):
                month_dates = [week_date for week_date in week_dates if week_date.month == int(record.month)]
                if not month_dates:
                    continue
                week = Week.create({
                    'asignacion_mensual_id': record.id,
                    'sequence': sequence,
                    'fecha_inicio': month_dates[0],
                    'fecha_fin': month_dates[-1],
                })
                for week_date in month_dates:
                    payload = preserved_payload.get(fields.Date.to_string(week_date), {})
                    day = Day.create({
                        'asignacion_mensual_id': record.id,
                        'semana_id': week.id,
                        'fecha': week_date,
                        'selected_for_seed': bool(payload.get('selected_for_seed')),
                    })
                    if payload.get('lines'):
                        self.env['portalgestor.asignacion.mensual.dia.linea'].with_context(
                            portalgestor_skip_seed_propagation=True
                        ).create([
                            {
                                'template_day_id': day.id,
                                'hora_inicio': line_data['hora_inicio'],
                                'hora_fin': line_data['hora_fin'],
                                'trabajador_id': line_data['trabajador_id'],
                            }
                            for line_data in payload['lines']
                        ])
        return True

    def _get_template_target_specs(self):
        self.ensure_one()
        if self.schedule_type != 'monthly_template':
            return {}
        target_specs = defaultdict(list)
        for day in self.template_day_ids.sorted(key=lambda item: item.fecha or fields.Date.today()):
            if not day.fecha:
                continue
            target_date = day.fecha
            for line in day.template_day_line_ids.sorted(
                key=lambda item: (item.hora_inicio, item.hora_fin, item.id)
            ):
                target_specs[target_date].append({
                    'template_day_id': day.id,
                    'template_day_line_id': line.id,
                    'hora_inicio': line.hora_inicio,
                    'hora_fin': line.hora_fin,
                    'trabajador_id': line.trabajador_id.id,
                    'trabajador': line.trabajador_id,
                })
        return target_specs

    def _run_template_target_checks(self, target_specs):
        self.ensure_one()
        if self.usuario_id.baja:
            raise ValidationError(_("No puedes confirmar un horario para un usuario dado de baja."))
        if not self.usuario_id.has_ap_service:
            raise ValidationError(_("Solo puedes confirmar horarios para usuarios con el servicio AP activo."))

        target_zone = self.usuario_id.zona_trabajo_id
        worker_dates = defaultdict(list)
        for target_date, lines in target_specs.items():
            workers = self.env['trabajadores.trabajador'].browse([line['trabajador_id'] for line in lines]).exists()
            vacaciones = self.env['trabajadores.vacacion'].search([
                ('trabajador_id', 'in', workers.ids),
                ('date_start', '<=', target_date),
                ('date_stop', '>=', target_date),
            ])
            vacaciones_by_worker = {vacacion.trabajador_id.id: vacacion for vacacion in vacaciones}
            lines_by_worker = defaultdict(list)
            for line in lines:
                trabajador = line['trabajador']
                if trabajador.baja:
                    raise ValidationError(
                        _("El AP %(worker)s esta dado de baja y no se puede confirmar en %(date)s.")
                        % {
                            'worker': trabajador.display_name or trabajador.name,
                            'date': fields.Date.to_string(target_date),
                        }
                    )
                if target_zone and target_zone not in trabajador.zona_trabajo_ids:
                    raise ValidationError(
                        _("El AP %(worker)s no pertenece a la zona %(zone)s del usuario.")
                        % {
                            'worker': trabajador.display_name or trabajador.name,
                            'zone': target_zone.display_name or target_zone.name,
                        }
                    )
                if vacaciones_by_worker.get(trabajador.id):
                    raise ValidationError(
                        _("El AP %(worker)s tiene vacaciones el dia %(date)s y no se puede confirmar este horario.")
                        % {
                            'worker': trabajador.display_name or trabajador.name,
                            'date': fields.Date.to_string(target_date),
                        }
                    )
                worker_dates[(target_date, trabajador.id)].append(line)
                lines_by_worker[trabajador.id].append(line)

            for worker_lines in lines_by_worker.values():
                previous_line = False
                for line in sorted(worker_lines, key=lambda item: (item['hora_inicio'], item['hora_fin'], item['template_day_line_id'])):
                    if previous_line and line['hora_inicio'] < previous_line['hora_fin']:
                        trabajador = line['trabajador'] or previous_line['trabajador']
                        raise ValidationError(
                            _("El AP %(worker)s tiene dos tramos solapados dentro del mismo horario.")
                            % {
                                'worker': trabajador.display_name or trabajador.name,
                            }
                        )
                    previous_line = line
        return worker_dates

    def _collect_template_conflicts(self, target_specs):
        self.ensure_one()
        worker_dates = self._run_template_target_checks(target_specs)
        if not worker_dates:
            return {
                'protected': [],
                'overlapping': [],
                'protected_summary': '',
                'overlap_summary': '',
                'info_summary': '',
            }

        date_values = sorted({date_value for date_value, __worker_id in worker_dates})
        worker_ids = sorted({worker_id for __date_value, worker_id in worker_dates})
        other_lines = self.env['portalgestor.asignacion.linea'].search([
            ('fecha', 'in', date_values),
            ('trabajador_id', 'in', worker_ids),
        ]).filtered(
            lambda line: line.trabajador_id and line.asignacion_mensual_id.id != self.id
        )
        other_lines_by_key = defaultdict(list)
        for line in other_lines:
            other_lines_by_key[(line.fecha, line.trabajador_id.id)].append(line)
        user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
            other_lines.mapped('asignacion_id.usuario_id').ids
        )

        protected_ids = set()
        overlapping_ids = set()
        protected_summary = []
        overlap_summary = []
        info_summary = []
        info_seen = set()

        for key, template_lines in worker_dates.items():
            for template_line in template_lines:
                for conflict_line in other_lines_by_key.get(key, []):
                    overlap = min(template_line['hora_fin'], conflict_line.hora_fin) - max(
                        template_line['hora_inicio'],
                        conflict_line.hora_inicio,
                    )
                    conflict_user_name = (
                        user_view_data.get(conflict_line.asignacion_id.usuario_id.id, {}).get('display_name')
                        or conflict_line.asignacion_id.usuario_id.display_name
                    )
                    summary_line = _(
                        "%(date)s | %(worker)s | %(start)s - %(end)s | %(user)s"
                    ) % {
                        'date': fields.Date.to_string(key[0]),
                        'worker': template_line['trabajador'].display_name or template_line['trabajador'].name,
                        'start': self._format_hora(conflict_line.hora_inicio),
                        'end': self._format_hora(conflict_line.hora_fin),
                        'user': conflict_user_name,
                    }
                    if overlap > 0:
                        if not self.env.user._can_manage_target_group(conflict_line.asignacion_id.usuario_id.grupo):
                            if conflict_line.id not in protected_ids:
                                protected_ids.add(conflict_line.id)
                                protected_summary.append(summary_line)
                        else:
                            if conflict_line.id not in overlapping_ids:
                                overlapping_ids.add(conflict_line.id)
                                overlap_summary.append(summary_line)
                    elif not self.env.context.get('portalgestor_skip_template_same_day_warning'):
                        if conflict_line.id in info_seen:
                            continue
                        info_seen.add(conflict_line.id)
                        info_summary.append(
                            _("- %(worker)s | %(date)s | ya asignado a %(user)s de %(start)s a %(end)s") % {
                                'worker': template_line['trabajador'].display_name or template_line['trabajador'].name,
                                'date': fields.Date.to_string(key[0]),
                                'user': conflict_user_name,
                                'start': self._format_hora(conflict_line.hora_inicio),
                                'end': self._format_hora(conflict_line.hora_fin),
                            }
                        )

        return {
            'protected': sorted(protected_ids),
            'overlapping': sorted(overlapping_ids),
            'protected_summary': "\n".join(protected_summary),
            'overlap_summary': "\n".join(overlap_summary),
            'info_summary': "\n".join(info_summary),
        }

    def _apply_template_confirmation(self, target_specs):
        self.ensure_one()
        Assignment = self.env['portalgestor.asignacion']
        AssignmentLine = self.env['portalgestor.asignacion.linea']
        target_dates = sorted(target_specs)
        desired_line_ids = {
            line_data['template_day_line_id']
            for lines in target_specs.values()
            for line_data in lines
        }
        existing_generated_lines = AssignmentLine.search([
            ('asignacion_mensual_id', '=', self.id),
        ])
        existing_by_template_line = {
            line.asignacion_mensual_dia_linea_id.id: line
            for line in existing_generated_lines
            if line.asignacion_mensual_dia_linea_id
        }
        assignments_by_date = {}
        if target_dates:
            assignments_by_date = {
                assignment.fecha: assignment
                for assignment in Assignment.search([
                    ('usuario_id', '=', self.usuario_id.id),
                    ('fecha', 'in', target_dates),
                ])
            }

        for target_date in target_dates:
            assignment = assignments_by_date.get(target_date)
            if not assignment:
                assignment = Assignment.create({
                    'usuario_id': self.usuario_id.id,
                    'fecha': target_date,
                })
                assignments_by_date[target_date] = assignment
            for line_data in sorted(
                target_specs[target_date],
                key=lambda item: (item['hora_inicio'], item['hora_fin'], item['template_day_line_id'])
            ):
                vals = {
                    'asignacion_id': assignment.id,
                    'hora_inicio': line_data['hora_inicio'],
                    'hora_fin': line_data['hora_fin'],
                    'trabajador_id': line_data['trabajador_id'],
                    'asignacion_mensual_id': self.id,
                    'asignacion_mensual_linea_id': False,
                    'asignacion_mensual_dia_id': line_data['template_day_id'],
                    'asignacion_mensual_dia_linea_id': line_data['template_day_line_id'],
                }
                existing_line = existing_by_template_line.get(line_data['template_day_line_id'])
                if existing_line:
                    if (
                        existing_line.asignacion_id != assignment
                        or existing_line.hora_inicio != line_data['hora_inicio']
                        or existing_line.hora_fin != line_data['hora_fin']
                        or existing_line.trabajador_id.id != line_data['trabajador_id']
                        or existing_line.asignacion_mensual_dia_id.id != line_data['template_day_id']
                    ):
                        existing_line.with_context(
                            portalgestor_skip_fixed_sync=True,
                            portalgestor_skip_fixed_exception=True,
                        ).write(vals)
                    continue
                matching_manual_line = assignment.lineas_ids.filtered(
                    lambda line: not line.asignacion_mensual_id
                    and line.hora_inicio == line_data['hora_inicio']
                    and line.hora_fin == line_data['hora_fin']
                    and (
                        not line.trabajador_id
                        or line.trabajador_id.id == line_data['trabajador_id']
                    )
                )[:1]
                if matching_manual_line:
                    matching_manual_line.with_context(
                        portalgestor_skip_fixed_sync=True,
                        portalgestor_skip_fixed_exception=True,
                    ).write({
                        'trabajador_id': line_data['trabajador_id'],
                        'asignacion_mensual_id': self.id,
                        'asignacion_mensual_dia_id': line_data['template_day_id'],
                        'asignacion_mensual_dia_linea_id': line_data['template_day_line_id'],
                    })
                else:
                    AssignmentLine.with_context(
                        portalgestor_skip_fixed_sync=True,
                        portalgestor_skip_fixed_exception=True,
                    ).create(vals)

        lines_to_remove = existing_generated_lines.filtered(
            lambda line: line.asignacion_mensual_dia_linea_id.id not in desired_line_ids
        )
        if lines_to_remove:
            lines_to_remove.with_context(
                portalgestor_skip_fixed_sync=True,
                portalgestor_skip_fixed_exception=True,
            ).unlink()
        touched_assignments = (
            existing_generated_lines.mapped('asignacion_id')
            | self.asignacion_linea_ids.mapped('asignacion_id')
            | self.env['portalgestor.asignacion'].browse([assignment.id for assignment in assignments_by_date.values()])
        )
        touched_assignments.cleanup_empty_assignments()
        touched_assignments.exists().write({
            'confirmado': True,
            'gestor_owner_id': self.env.user.id,
            'edit_session_pending': False,
            'edit_snapshot_data': False,
        })
        self.write({
            'confirmado': True,
            'edit_session_pending': False,
            'edit_snapshot_data': False,
            'gestor_owner_id': self.env.user.id,
        })
        return True

    def action_verificar_y_confirmar(self):
        self.ensure_one()
        if self.schedule_type != 'monthly_template':
            return super().action_verificar_y_confirmar()

        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        self._ensure_monthly_template_structure()
        invalid_days = self.template_day_ids.filtered(lambda day: not day.fecha)
        if invalid_days:
            invalid_days.with_context(portalgestor_skip_seed_propagation=True).unlink()
        target_specs = self._get_template_target_specs()
        if not target_specs:
            raise ValidationError(_("Debes anadir al menos un tramo en la plantilla mensual."))

        batch_conflicts = self._collect_template_conflicts(target_specs)
        if batch_conflicts['protected']:
            return self._launch_batch_conflict_wizard(
                'protected_intecum_overlapping_batch',
                batch_conflicts['protected'],
                batch_conflicts['protected_summary'],
            )
        if batch_conflicts['overlapping']:
            return self._launch_batch_conflict_wizard(
                'overlapping_batch',
                batch_conflicts['overlapping'],
                batch_conflicts['overlap_summary'],
            )
        if batch_conflicts['info_summary'] and not self.env.context.get('portalgestor_skip_template_same_day_warning'):
            return self._launch_template_info_wizard(batch_conflicts['info_summary'])

        return self._apply_template_confirmation(target_specs)

    def _launch_template_info_wizard(self, summary_text):
        self.ensure_one()
        wizard = self.env['portalgestor.conflict.wizard'].create({
            'asignacion_mensual_id': self.id,
            'conflict_type': 'info_same_day',
            'info_resumen': summary_text,
        })
        return {
            'name': 'Aviso de Asignaciones del Mismo Dia',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.conflict.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


class AsignacionMensualSemana(models.Model):
    _name = 'portalgestor.asignacion.mensual.semana'
    _description = 'Semana de plantilla mensual'
    _order = 'sequence, id'

    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Plantilla mensual',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Semana', required=True, default=1)
    fecha_inicio = fields.Date(string='Inicio', required=True)
    fecha_fin = fields.Date(string='Fin', required=True)
    name = fields.Char(string='Semana', compute='_compute_name')
    template_day_ids = fields.One2many(
        'portalgestor.asignacion.mensual.dia',
        'semana_id',
        string='Dias',
    )
    template_locked = fields.Boolean(
        compute='_compute_template_locked',
        string='Bloqueada',
    )

    @api.model
    def _context_int(self, key):
        value = self.env.context.get(key)
        if isinstance(value, int):
            return value
        try:
            return int(value) if value else False
        except (TypeError, ValueError):
            return False

    @api.model_create_multi
    def create(self, vals_list):
        default_monthly_id = self._context_int('default_asignacion_mensual_id')
        prepared_vals_list = []
        for vals in vals_list:
            values = dict(vals)
            if not values.get('asignacion_mensual_id') and default_monthly_id:
                values['asignacion_mensual_id'] = default_monthly_id
            prepared_vals_list.append(values)
        return super().create(prepared_vals_list)

    @api.depends('sequence', 'fecha_inicio', 'fecha_fin')
    def _compute_name(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin:
                record.name = _("Semana %(sequence)s | %(start)s - %(end)s") % {
                    'sequence': record.sequence,
                    'start': fields.Date.to_string(record.fecha_inicio),
                    'end': fields.Date.to_string(record.fecha_fin),
                }
            else:
                record.name = _("Semana %s") % record.sequence

    @api.depends(
        'asignacion_mensual_id.template_content_locked',
        'asignacion_mensual_id.schedule_type',
    )
    def _compute_template_locked(self):
        for record in self:
            record.template_locked = bool(
                record.asignacion_mensual_id.schedule_type != 'monthly_template'
                or record.asignacion_mensual_id.template_content_locked
            )

    def _build_copy_feedback_action(self, message, notif_type='success', title=False, reload=False):
        params = {
            'message': message,
            'type': notif_type,
            'sticky': False,
        }
        if title:
            params['title'] = title
        if reload:
            params['next'] = {'type': 'ir.actions.client', 'tag': 'reload'}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': params,
        }

    def action_copy_to_next_week(self):
        self.ensure_one()
        monthly = self.asignacion_mensual_id
        if not monthly:
            return self._build_copy_feedback_action(
                _("Guarda la plantilla mensual antes de copiar semanas."),
                notif_type='warning',
                title=_("Copia no realizada"),
            )
        monthly._ensure_current_user_can_manage_users(monthly.mapped('usuario_id'))
        next_week = monthly.template_week_ids.filtered(lambda week: week.sequence == self.sequence + 1)[:1]
        if not next_week:
            return self._build_copy_feedback_action(
                _("Esta es la ultima semana del mes visible en la plantilla. No hay una semana siguiente a la que copiar."),
                notif_type='warning',
                title=_("Copia no realizada"),
            )

        source_days = self.template_day_ids.filtered('template_day_line_ids')
        if not source_days:
            return self._build_copy_feedback_action(
                _("La semana %(week)s no tiene tramos configurados todavia.")
                % {'week': self.sequence},
                notif_type='warning',
                title=_("Nada que copiar"),
            )

        target_by_weekday = {
            day.weekday_index: day
            for day in next_week.template_day_ids
        }
        copied_days = 0
        copied_lines = 0
        skipped_days = 0
        for source_day in source_days:
            target_day = target_by_weekday.get(source_day.weekday_index)
            if not target_day:
                skipped_days += 1
                continue
            target_day._replace_with_source_day(source_day, preserve_selection=True)
            copied_days += 1
            copied_lines += len(source_day.template_day_line_ids)

        if not copied_days:
            return self._build_copy_feedback_action(
                _("No se ha podido copiar ningun dia porque la semana destino no comparte dias equivalentes dentro del mes."),
                notif_type='warning',
                title=_("Copia no realizada"),
            )

        message = _(
            "Se copiaron %(days)s dias y %(lines)s tramos de la semana %(source)s a la semana %(target)s."
        ) % {
            'days': copied_days,
            'lines': copied_lines,
            'source': self.sequence,
            'target': next_week.sequence,
        }
        if skipped_days:
            message += "\n" + _(
                "%(days)s dias no se copiaron porque no existen en la semana destino."
            ) % {'days': skipped_days}
        return self._build_copy_feedback_action(
            message,
            notif_type='success',
            title=_("Copia realizada"),
            reload=True,
        )


class AsignacionMensualDia(models.Model):
    _name = 'portalgestor.asignacion.mensual.dia'
    _description = 'Dia de plantilla mensual'
    _order = 'fecha, id'

    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Plantilla mensual',
        ondelete='cascade',
        index=True,
    )
    semana_id = fields.Many2one(
        'portalgestor.asignacion.mensual.semana',
        string='Semana',
        required=True,
        ondelete='cascade',
        index=True,
    )
    fecha = fields.Date(string='Fecha', required=True, index=True)
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        string='Zona del Usuario',
        compute='_compute_user_context_fields',
        store=True,
        readonly=True,
        index=True,
    )
    usuario_localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad del Usuario',
        compute='_compute_user_context_fields',
        store=True,
        readonly=True,
    )
    weekday_index = fields.Integer(string='Dia semana', compute='_compute_weekday_fields', store=True)
    weekday_label = fields.Char(string='Dia', compute='_compute_weekday_fields', store=True)
    selected_for_seed = fields.Boolean(string='Sembrar semana')
    seed_source_day_id = fields.Many2one(
        'portalgestor.asignacion.mensual.dia',
        string='Origen de copia',
        ondelete='set null',
        copy=False,
    )
    seed_is_pristine = fields.Boolean(string='Copia intacta', default=False, copy=False)
    template_day_line_ids = fields.One2many(
        'portalgestor.asignacion.mensual.dia.linea',
        'template_day_id',
        string='Tramos',
    )
    line_count = fields.Integer(string='Tramos', compute='_compute_line_summary')
    line_summary = fields.Char(string='Resumen', compute='_compute_line_summary')
    template_locked = fields.Boolean(
        compute='_compute_template_locked',
        string='Bloqueado',
    )

    def _get_template_parent(self):
        self.ensure_one()
        return self.asignacion_mensual_id or self.semana_id.asignacion_mensual_id

    @api.depends('fecha')
    def _compute_weekday_fields(self):
        for record in self:
            if not record.fecha:
                record.weekday_index = 0
                record.weekday_label = ''
                continue
            weekday_index = fields.Date.to_date(record.fecha).weekday()
            record.weekday_index = weekday_index
            record.weekday_label = WEEKDAY_LABELS.get(weekday_index, '')

    @api.depends(
        'asignacion_mensual_id',
        'asignacion_mensual_id.usuario_zona_trabajo_id',
        'asignacion_mensual_id.usuario_localidad_id',
        'semana_id.asignacion_mensual_id',
        'semana_id.asignacion_mensual_id.usuario_zona_trabajo_id',
        'semana_id.asignacion_mensual_id.usuario_localidad_id',
    )
    def _compute_user_context_fields(self):
        for record in self:
            template_parent = record._get_template_parent()
            record.usuario_zona_trabajo_id = template_parent.usuario_zona_trabajo_id if template_parent else False
            record.usuario_localidad_id = template_parent.usuario_localidad_id if template_parent else False

    @api.depends('template_day_line_ids', 'template_day_line_ids.hora_inicio', 'template_day_line_ids.hora_fin', 'template_day_line_ids.trabajador_id')
    def _compute_line_summary(self):
        for record in self:
            lines = record.template_day_line_ids.sorted(key=lambda item: (item.hora_inicio, item.hora_fin, item.id))
            record.line_count = len(lines)
            record.line_summary = ' | '.join(
                '%s-%s %s' % (
                    AsignacionMensual._format_hora(line.hora_inicio),
                    AsignacionMensual._format_hora(line.hora_fin),
                    line.trabajador_id.display_name or line.trabajador_id.name,
                )
                for line in lines
            )

    @api.depends(
        'asignacion_mensual_id',
        'semana_id.asignacion_mensual_id',
        'asignacion_mensual_id.template_content_locked',
        'asignacion_mensual_id.schedule_type',
        'semana_id.asignacion_mensual_id.template_content_locked',
        'semana_id.asignacion_mensual_id.schedule_type',
    )
    def _compute_template_locked(self):
        for record in self:
            template_parent = record._get_template_parent()
            if not template_parent:
                record.template_locked = False
                continue
            record.template_locked = bool(
                template_parent.schedule_type != 'monthly_template'
                or template_parent.template_content_locked
            )

    @api.model_create_multi
    def create(self, vals_list):
        default_monthly_id = self.env['portalgestor.asignacion.mensual.semana']._context_int(
            'default_asignacion_mensual_id'
        )
        default_week_id = self.env['portalgestor.asignacion.mensual.semana']._context_int(
            'default_semana_id'
        )
        prepared_vals_list = []
        for vals in vals_list:
            values = dict(vals)
            if not values.get('semana_id') and default_week_id:
                values['semana_id'] = default_week_id
            if not values.get('asignacion_mensual_id') and default_monthly_id:
                values['asignacion_mensual_id'] = default_monthly_id
            if not values.get('asignacion_mensual_id') and values.get('semana_id'):
                week = self.env['portalgestor.asignacion.mensual.semana'].browse(values['semana_id']).exists()
                if week and week.asignacion_mensual_id:
                    values['asignacion_mensual_id'] = week.asignacion_mensual_id.id
            prepared_vals_list.append(values)
        return super().create(prepared_vals_list)

    def write(self, vals):
        values = dict(vals)
        if not values.get('asignacion_mensual_id') and values.get('semana_id'):
            week = self.env['portalgestor.asignacion.mensual.semana'].browse(values['semana_id']).exists()
            if week and week.asignacion_mensual_id:
                values['asignacion_mensual_id'] = week.asignacion_mensual_id.id
        result = super().write(values)
        if 'selected_for_seed' in values and not self.env.context.get('portalgestor_skip_seed_propagation'):
            self._apply_seed_selection()
        return result

    def _clear_seed_link(self):
        self.write({
            'seed_source_day_id': False,
            'seed_is_pristine': False,
        })

    def _replace_with_source_day(self, source_day, preserve_selection=False):
        self.ensure_one()
        if self == source_day:
            return True
        DayLine = self.env['portalgestor.asignacion.mensual.dia.linea']
        copy_context = dict(self.env.context, portalgestor_skip_seed_propagation=True)
        self.template_day_line_ids.with_context(**copy_context).unlink()
        if source_day.template_day_line_ids:
            DayLine.with_context(**copy_context).create([
                {
                    'template_day_id': self.id,
                    'hora_inicio': line.hora_inicio,
                    'hora_fin': line.hora_fin,
                    'trabajador_id': line.trabajador_id.id,
                }
                for line in source_day.template_day_line_ids.sorted(
                    key=lambda item: (item.hora_inicio, item.hora_fin, item.id)
                )
            ])
        write_vals = {
            'seed_source_day_id': source_day.id,
            'seed_is_pristine': True,
        }
        if not preserve_selection:
            write_vals['selected_for_seed'] = self.selected_for_seed
        self.with_context(**copy_context).write(write_vals)
        return True

    def _apply_seed_selection(self):
        for record in self:
            if not record.selected_for_seed or record.seed_source_day_id:
                continue
            if record.template_day_line_ids:
                record._propagate_seed_changes(initial_seed=True)
                continue
            source_day = record.semana_id.template_day_ids.filtered(
                lambda day: day.id != record.id
                and day.selected_for_seed
                and day.template_day_line_ids
                and not day.seed_source_day_id
            )[:1]
            if source_day:
                record._replace_with_source_day(source_day, preserve_selection=True)
        return True

    def _propagate_seed_changes(self, initial_seed=False):
        if self.env.context.get('portalgestor_skip_seed_propagation'):
            return True
        for record in self:
            if not record.selected_for_seed or record.seed_source_day_id:
                continue
            targets = record.semana_id.template_day_ids.filtered(
                lambda day: day.id != record.id and day.selected_for_seed and (
                    (initial_seed and not day.template_day_line_ids)
                    or (day.seed_source_day_id.id == record.id and day.seed_is_pristine)
                )
            )
            for target in targets:
                target._replace_with_source_day(record, preserve_selection=True)
        return True


class AsignacionMensualDiaLinea(models.Model):
    _name = 'portalgestor.asignacion.mensual.dia.linea'
    _description = 'Tramo de plantilla mensual'
    _order = 'hora_inicio, hora_fin, id'

    template_day_id = fields.Many2one(
        'portalgestor.asignacion.mensual.dia',
        string='Dia de plantilla',
        required=True,
        ondelete='cascade',
        index=True,
    )
    asignacion_mensual_id = fields.Many2one(
        related='template_day_id.asignacion_mensual_id',
        string='Plantilla mensual',
        store=True,
        readonly=True,
        index=True,
    )
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        string='Zona del Usuario',
        compute='_compute_user_context_fields',
        store=True,
        readonly=True,
        index=True,
    )
    usuario_localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad del Usuario',
        compute='_compute_user_context_fields',
        store=True,
        readonly=True,
    )
    fecha = fields.Date(
        related='template_day_id.fecha',
        string='Fecha',
        store=True,
        readonly=True,
        index=True,
    )
    hora_inicio = fields.Float(string='Hora Inicio', required=True)
    hora_fin = fields.Float(string='Hora Fin', required=True)
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        ondelete='restrict',
        index=True,
    )
    template_locked = fields.Boolean(
        compute='_compute_template_locked',
        string='Bloqueado',
    )

    def _get_template_parent(self):
        self.ensure_one()
        return (
            self.asignacion_mensual_id
            or self.template_day_id.asignacion_mensual_id
            or self.template_day_id.semana_id.asignacion_mensual_id
        )

    @api.depends(
        'asignacion_mensual_id',
        'asignacion_mensual_id.usuario_zona_trabajo_id',
        'asignacion_mensual_id.usuario_localidad_id',
        'template_day_id',
        'template_day_id.usuario_zona_trabajo_id',
        'template_day_id.usuario_localidad_id',
        'template_day_id.semana_id.asignacion_mensual_id',
        'template_day_id.semana_id.asignacion_mensual_id.usuario_zona_trabajo_id',
        'template_day_id.semana_id.asignacion_mensual_id.usuario_localidad_id',
    )
    def _compute_user_context_fields(self):
        for record in self:
            if record.template_day_id:
                record.usuario_zona_trabajo_id = record.template_day_id.usuario_zona_trabajo_id
                record.usuario_localidad_id = record.template_day_id.usuario_localidad_id
                continue
            template_parent = record._get_template_parent()
            record.usuario_zona_trabajo_id = template_parent.usuario_zona_trabajo_id if template_parent else False
            record.usuario_localidad_id = template_parent.usuario_localidad_id if template_parent else False

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_mensual_dia_linea_dia_fecha_idx',
            tablename=self._table,
            expressions=['template_day_id', 'fecha'],
        )

    @api.depends(
        'asignacion_mensual_id',
        'template_day_id.asignacion_mensual_id',
        'template_day_id.semana_id.asignacion_mensual_id',
        'asignacion_mensual_id.template_content_locked',
        'asignacion_mensual_id.schedule_type',
        'template_day_id.asignacion_mensual_id.template_content_locked',
        'template_day_id.asignacion_mensual_id.schedule_type',
        'template_day_id.semana_id.asignacion_mensual_id.template_content_locked',
        'template_day_id.semana_id.asignacion_mensual_id.schedule_type',
    )
    def _compute_template_locked(self):
        for record in self:
            template_parent = record._get_template_parent()
            if not template_parent:
                record.template_locked = False
                continue
            record.template_locked = bool(
                template_parent.schedule_type != 'monthly_template'
                or template_parent.template_content_locked
            )

    def _ensure_current_user_can_manage_parent_records(self, parent_records):
        self.env['portalgestor.asignacion.mensual']._ensure_current_user_can_manage_users(
            parent_records.mapped('usuario_id')
        )

    @api.model_create_multi
    def create(self, vals_list):
        default_day_id = self.env['portalgestor.asignacion.mensual.semana']._context_int(
            'default_template_day_id'
        )
        prepared_vals_list = []
        for vals in vals_list:
            values = dict(vals)
            if not values.get('template_day_id') and default_day_id:
                values['template_day_id'] = default_day_id
            prepared_vals_list.append(values)

        day_ids = [vals.get('template_day_id') for vals in prepared_vals_list if vals.get('template_day_id')]
        target_days = self.env['portalgestor.asignacion.mensual.dia'].browse(day_ids).exists()
        if target_days:
            self._ensure_current_user_can_manage_parent_records(target_days.mapped('asignacion_mensual_id'))
        had_lines_before = {
            day.id: bool(day.template_day_line_ids)
            for day in target_days
        }
        records = super().create(prepared_vals_list)
        if self.env.context.get('portalgestor_skip_seed_propagation'):
            return records

        changed_days = records.mapped('template_day_id')
        for day in changed_days:
            if day.seed_source_day_id:
                day._clear_seed_link()
                continue
            day._propagate_seed_changes(initial_seed=not had_lines_before.get(day.id))
        return records

    def write(self, vals):
        target_days = self.mapped('template_day_id')
        self._ensure_current_user_can_manage_parent_records(target_days.mapped('asignacion_mensual_id'))
        result = super().write(vals)
        if self.env.context.get('portalgestor_skip_seed_propagation'):
            return result
        changed_days = self.mapped('template_day_id')
        for day in changed_days:
            if day.seed_source_day_id:
                day._clear_seed_link()
            else:
                day._propagate_seed_changes(initial_seed=False)
        return result

    def unlink(self):
        target_days = self.mapped('template_day_id')
        self._ensure_current_user_can_manage_parent_records(target_days.mapped('asignacion_mensual_id'))
        result = super().unlink()
        if self.env.context.get('portalgestor_skip_seed_propagation'):
            return result
        for day in target_days.exists():
            if day.seed_source_day_id:
                day._clear_seed_link()
            else:
                day._propagate_seed_changes(initial_seed=False)
        return result

    @api.constrains('hora_inicio', 'hora_fin')
    def _check_horas(self):
        for record in self:
            if record.hora_inicio < 0 or record.hora_inicio >= 24:
                raise ValidationError(_("La hora de inicio debe estar entre 00:00 y 23:59."))
            if record.hora_fin < 0 or record.hora_fin >= 24:
                raise ValidationError(_("La hora de fin debe estar entre 00:00 y 23:59."))
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError(_("La hora de inicio debe ser anterior a la hora de fin."))


class AsignacionLinea(models.Model):
    _inherit = 'portalgestor.asignacion.linea'

    asignacion_mensual_dia_id = fields.Many2one(
        'portalgestor.asignacion.mensual.dia',
        string='Dia de plantilla mensual',
        ondelete='set null',
        index=True,
    )
    asignacion_mensual_dia_linea_id = fields.Many2one(
        'portalgestor.asignacion.mensual.dia.linea',
        string='Tramo de plantilla mensual',
        ondelete='set null',
        index=True,
    )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_mensual_dia_fecha_idx',
            tablename=self._table,
            expressions=['asignacion_mensual_dia_id', 'fecha'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_mensual_dia_linea_fecha_idx',
            tablename=self._table,
            expressions=['asignacion_mensual_dia_linea_id', 'fecha'],
        )

    def _get_assignment_fixed_monthly_ids(self, assignments):
        monthly_ids_by_assignment = {}
        for assignment in assignments.exists():
            monthly_ids = set(
                assignment.lineas_ids.filtered('asignacion_mensual_linea_id').mapped('asignacion_mensual_id').ids
            )
            if monthly_ids:
                monthly_ids_by_assignment[assignment.id] = monthly_ids
        return monthly_ids_by_assignment

    def _merge_assignment_fixed_monthly_ids(self, monthly_ids_by_assignment, assignments):
        for assignment in assignments.exists():
            if assignment.id not in monthly_ids_by_assignment:
                monthly_ids_by_assignment[assignment.id] = set()
            monthly_ids_by_assignment[assignment.id].update(
                assignment.lineas_ids.filtered('asignacion_mensual_linea_id').mapped('asignacion_mensual_id').ids
            )
        return monthly_ids_by_assignment
