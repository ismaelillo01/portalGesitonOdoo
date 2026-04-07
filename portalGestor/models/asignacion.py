# -*- coding: utf-8 -*-
import json
from collections import defaultdict
from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import create_index

PORTALGESTOR_CALENDAR_CHANNEL = 'portalgestor.calendar'
PORTALGESTOR_CALENDAR_NOTIFICATION = 'portalgestor.calendar.updated'


class Asignacion(models.Model):
    _name = 'portalgestor.asignacion'
    _description = 'Asignacion de Horario a Usuario'
    _order = 'fecha desc, id desc'

    _sql_constraints = [
        (
            'unique_usuario_fecha',
            'unique(usuario_id, fecha)',
            'Ya existe una asignacion para este usuario en esta fecha.',
        )
    ]

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
    )
    usuario_grupo = fields.Selection(
        related='usuario_id.grupo',
        string='Grupo del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today, index=True)
    lineas_ids = fields.One2many('portalgestor.asignacion.linea', 'asignacion_id', string='Horarios')
    confirmado = fields.Boolean(string='Horario Confirmado', default=False)
    gestor_owner_id = fields.Many2one(
        'res.users',
        string='Gestor propietario',
        default=lambda self: self.env.user,
        ondelete='set null',
        index=True,
        copy=False,
    )
    gestor_owner_label = fields.Char(
        string='Gestor propietario',
        compute='_compute_gestor_owner_label',
    )
    edit_session_pending = fields.Boolean(string='Edicion pendiente', default=False, copy=False)
    edit_snapshot_data = fields.Text(string='Snapshot de edicion', copy=False)
    trabajador_calendar_filter_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        compute='_compute_calendar_worker_fields',
        search='_search_trabajador_calendar_filter_id',
    )
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        compute='_compute_calendar_worker_fields',
        search='_search_trabajador_calendar_filter_id',
    )
    trabajador_resumen = fields.Char(
        string='AP',
        compute='_compute_lineas_resumen',
        store=True,
    )
    rango_horas_resumen = fields.Char(
        string='Rango de horas',
        compute='_compute_lineas_resumen',
        store=True,
    )
    calendar_popover_html = fields.Html(
        string='Detalle del horario',
        compute='_compute_calendar_popover_html',
        sanitize=False,
    )
    calendar_bucket_type = fields.Selection(
        selection=[
            ('pending', 'Por asignar'),
            ('missing', 'Faltantes'),
            ('completed', 'Completados'),
        ],
        string='Tipo de bloque de calendario',
        compute='_compute_calendar_bucket_type',
        store=True,
        readonly=True,
        index=True,
    )
    color_calendario = fields.Integer(
        string='Color Calendario',
        compute='_compute_color_calendario',
        store=True,
    )
    manager_edit_blocked = fields.Boolean(
        string='Edicion bloqueada para el gestor actual',
        compute='_compute_manager_edit_blocked',
    )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_asig_fecha_id_idx',
            tablename=self._table,
            expressions=['fecha desc', 'id desc'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_asig_grupo_fecha_id_idx',
            tablename=self._table,
            expressions=['usuario_grupo', 'fecha desc', 'id desc'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_asig_fecha_bucket_idx',
            tablename=self._table,
            expressions=['fecha', 'calendar_bucket_type'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_asig_owner_fecha_idx',
            tablename=self._table,
            expressions=['gestor_owner_id', 'fecha desc', 'id desc'],
        )
        self.env.cr.execute(
            f"""
                UPDATE {self._table}
                   SET gestor_owner_id = COALESCE(write_uid, create_uid)
                 WHERE gestor_owner_id IS NULL
            """
        )

    @api.depends('usuario_id.name', 'fecha')
    def _compute_name(self):
        for record in self:
            if record.usuario_id and record.fecha:
                record.name = record.usuario_id.name
            else:
                record.name = _("Nueva Asignacion")

    @api.constrains('usuario_id')
    def _check_usuario_has_ap_service(self):
        for record in self:
            if record.usuario_id and not record.usuario_id.has_ap_service:
                raise ValidationError(_("Solo puedes asignar horarios a usuarios con el servicio AP activo."))

    @staticmethod
    def _calculate_calendar_bucket_type(lineas):
        if not lineas:
            return 'pending'

        total_lineas = len(lineas)
        lineas_asignadas = sum(1 for linea in lineas if linea.trabajador_id)
        if lineas_asignadas == 0:
            return 'pending'
        if lineas_asignadas == total_lineas:
            return 'completed'
        return 'missing'

    @api.depends('lineas_ids', 'lineas_ids.trabajador_id')
    def _compute_calendar_bucket_type(self):
        for record in self:
            record.calendar_bucket_type = self._calculate_calendar_bucket_type(record.lineas_ids)

    @api.depends('calendar_bucket_type')
    def _compute_color_calendario(self):
        bucket_map = self._get_calendar_bucket_map()
        default_color = bucket_map['pending']['color']
        for record in self:
            record.color_calendario = bucket_map.get(record.calendar_bucket_type, {}).get('color', default_color)

    @api.depends('usuario_grupo')
    def _compute_manager_edit_blocked(self):
        for record in self:
            record.manager_edit_blocked = not self.env.user._can_manage_target_group(record.usuario_grupo)

    @api.depends('gestor_owner_id')
    def _compute_gestor_owner_label(self):
        for record in self:
            record.gestor_owner_label = record._get_owner_display_name()

    @api.depends('lineas_ids.trabajador_id')
    def _compute_calendar_worker_fields(self):
        for record in self:
            trabajador = record.lineas_ids.mapped('trabajador_id')[:1]
            record.trabajador_calendar_filter_id = trabajador
            record.trabajador_id = trabajador

    @api.depends(
        'lineas_ids',
        'lineas_ids.trabajador_id',
        'lineas_ids.hora_inicio',
        'lineas_ids.hora_fin',
    )
    def _compute_lineas_resumen(self):
        for record in self:
            lineas_ordenadas = record.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id))
            if not lineas_ordenadas:
                record.trabajador_resumen = ''
                record.rango_horas_resumen = ''
                continue

            record.trabajador_resumen = ' | '.join(
                linea.trabajador_id.name or 'Sin asignar'
                for linea in lineas_ordenadas
            )
            record.rango_horas_resumen = ' | '.join(
                f"{self._format_hora(linea.hora_inicio)} - {self._format_hora(linea.hora_fin)}"
                for linea in lineas_ordenadas
            )

    @api.depends(
        'lineas_ids',
        'lineas_ids.trabajador_id',
        'lineas_ids.hora_inicio',
        'lineas_ids.hora_fin',
    )
    def _compute_calendar_popover_html(self):
        for record in self:
            lineas_ordenadas = record.lineas_ids.sorted(
                key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id)
            )
            if not lineas_ordenadas:
                record.calendar_popover_html = (
                    '<div class="o_portalgestor_calendar_detail">'
                    '<div class="o_portalgestor_calendar_detail_empty">Sin tramos asignados</div>'
                    '</div>'
                )
                continue

            rows = []
            for linea in lineas_ordenadas:
                rango = f"{self._format_hora(linea.hora_inicio)} - {self._format_hora(linea.hora_fin)}"
                trabajador = linea.trabajador_id.display_name or 'Sin asignar'
                rows.append(
                    '<div class="o_portalgestor_calendar_detail_row">'
                    f'<span class="o_portalgestor_calendar_detail_hours">{escape(rango)}</span>'
                    '<span class="o_portalgestor_calendar_detail_sep">||</span>'
                    f'<span class="o_portalgestor_calendar_detail_worker">{escape(trabajador)}</span>'
                    '</div>'
                )
            owner_html = ''
            if record.gestor_owner_id:
                owner_html = (
                    '<div class="o_portalgestor_calendar_detail_owner">'
                    '<span class="o_portalgestor_calendar_detail_owner_label">Gestor</span>'
                    f'<span class="o_portalgestor_calendar_detail_owner_value">{escape(record.gestor_owner_id.display_name or record.gestor_owner_id.name)}</span>'
                    '</div>'
                )
            record.calendar_popover_html = (
                '<div class="o_portalgestor_calendar_detail">'
                + ''.join(rows)
                + owner_html
                + '</div>'
            )

    @staticmethod
    def _format_hora(hour_float):
        return '%02d:%02d' % (int(hour_float), int((hour_float % 1) * 60))

    def _get_calendar_bucket_type(self):
        self.ensure_one()
        return self.calendar_bucket_type or self._calculate_calendar_bucket_type(self.lineas_ids)

    @api.model
    def _get_calendar_owner_filter_domain(self):
        if self.env.context.get('portalgestor_only_my_schedules'):
            return [('gestor_owner_id', '=', self.env.user.id)]
        return []

    def _get_owner_display_name(self):
        self.ensure_one()
        return self.gestor_owner_id.display_name or self.gestor_owner_id.name or _('Sin gestor')

    def _apply_confirmation_as_current_manager(self):
        if not self:
            return True
        self.write({
            'confirmado': True,
            'edit_session_pending': False,
            'edit_snapshot_data': False,
            'gestor_owner_id': self.env.user.id,
        })
        return True

    def _ensure_current_user_can_manage_users(self, users):
        forbidden_users = users.filtered(
            lambda usuario: not self.env.user._can_manage_target_group(usuario.grupo)
        )
        if forbidden_users:
            raise AccessError(
                _("Los gestores Agusto no pueden crear, modificar ni eliminar horarios de usuarios de Intecum.")
            )

    @api.model
    def _search_trabajador_calendar_filter_id(self, operator, value):
        worker_ids = value if isinstance(value, (list, tuple, set)) else [value]
        worker_ids = [worker_id for worker_id in worker_ids if worker_id]
        if not worker_ids:
            return [('id', '=', 0)] if operator in ('=', 'in') else []

        domain = [('lineas_ids.trabajador_id', 'in', worker_ids)]
        if operator in ('=', 'in'):
            return domain
        if operator in ('!=', 'not in'):
            return [('id', 'not in', self.search(domain).ids)]
        return [('id', '=', 0)]

    @api.model
    def _get_calendar_bucket_map(self):
        return {
            'pending': {
                'color': 10,
                'label': 'Por asignar',
                'priority': 0,
            },
            'missing': {
                'color': 3,
                'label': 'Faltantes',
                'priority': 1,
            },
            'completed': {
                'color': 1,
                'label': 'Completados',
                'priority': 2,
            },
        }

    @api.model
    def _sort_calendar_bucket_types(self, bucket_types):
        bucket_map = self._get_calendar_bucket_map()
        return sorted(
            bucket_types,
            key=lambda bucket_type: bucket_map.get(bucket_type, {}).get('priority', 99),
        )

    def _get_calendar_realtime_snapshot(self):
        snapshot = {}
        for record in self.exists().filtered('confirmado'):
            snapshot[record.id] = {
                'date': fields.Date.to_string(record.fecha),
                'bucket_type': record._get_calendar_bucket_type(),
            }
        return snapshot

    def _get_edit_snapshot_payload(self):
        self.ensure_one()
        return {
            'confirmado': bool(self.confirmado),
            'fecha': fields.Date.to_string(self.fecha) if self.fecha else False,
            'usuario_id': self.usuario_id.id or False,
            'lineas': [
                {
                    'hora_inicio': linea.hora_inicio,
                    'hora_fin': linea.hora_fin,
                    'trabajador_id': linea.trabajador_id.id or False,
                    'asignacion_mensual_id': linea.asignacion_mensual_id.id or False,
                    'asignacion_mensual_linea_id': linea.asignacion_mensual_linea_id.id or False,
                }
                for linea in self.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id))
            ],
        }

    def _set_edit_snapshot(self):
        for record in self:
            if record.edit_session_pending:
                continue
            record.write({
                'edit_session_pending': True,
                'edit_snapshot_data': json.dumps(record._get_edit_snapshot_payload()),
            })

    def _clear_edit_snapshot(self):
        if not self:
            return
        self.write({
            'edit_session_pending': False,
            'edit_snapshot_data': False,
        })

    def _restore_edit_snapshot(self):
        AsignacionLinea = self.env['portalgestor.asignacion.linea']
        for record in self.exists().filtered(lambda assignment: assignment.edit_session_pending and assignment.edit_snapshot_data):
            before_state = record._get_calendar_realtime_snapshot()
            snapshot = json.loads(record.edit_snapshot_data)
            current_date = record.fecha
            snapshot_date = fields.Date.to_date(snapshot.get('fecha'))
            snapshot_monthly_ids = {
                line_data.get('asignacion_mensual_id')
                for line_data in snapshot.get('lineas', [])
                if line_data.get('asignacion_mensual_id')
            }

            record.lineas_ids.with_context(
                portalgestor_skip_calendar_notify=True,
                portalgestor_skip_fixed_exception=True,
            ).unlink()
            record.with_context(portalgestor_skip_calendar_notify=True).write({
                'usuario_id': snapshot.get('usuario_id') or False,
                'fecha': snapshot_date,
                'confirmado': bool(snapshot.get('confirmado', True)),
            })

            line_values = []
            for line_data in snapshot.get('lineas', []):
                line_values.append({
                    'asignacion_id': record.id,
                    'hora_inicio': line_data['hora_inicio'],
                    'hora_fin': line_data['hora_fin'],
                    'trabajador_id': line_data.get('trabajador_id') or False,
                    'asignacion_mensual_id': line_data.get('asignacion_mensual_id') or False,
                    'asignacion_mensual_linea_id': line_data.get('asignacion_mensual_linea_id') or False,
                })
            if line_values:
                AsignacionLinea.with_context(
                    portalgestor_skip_calendar_notify=True,
                    portalgestor_skip_fixed_exception=True,
                ).create(line_values)

            if snapshot_monthly_ids:
                exceptions = self.env['portalgestor.asignacion.mensual.excepcion'].search([
                    ('asignacion_mensual_id', 'in', sorted(snapshot_monthly_ids)),
                    ('fecha', 'in', list({date_value for date_value in [current_date, snapshot_date] if date_value})),
                ])
                if exceptions:
                    exceptions.unlink()
                monthly_records = self.env['portalgestor.asignacion.mensual'].browse(sorted(snapshot_monthly_ids)).exists()
                for monthly in monthly_records:
                    has_unconfirmed_generated = monthly.asignacion_linea_ids.mapped('asignacion_id').filtered(
                        lambda asignacion: not asignacion.confirmado
                    )
                    if not has_unconfirmed_generated:
                        monthly.write({'confirmado': True})

            record.with_context(portalgestor_skip_calendar_notify=True).write({
                'edit_session_pending': False,
                'edit_snapshot_data': False,
            })
            record._send_calendar_update_notification(
                record._build_calendar_update_payload(
                    before_state=before_state,
                    after_state=record.exists()._get_calendar_realtime_snapshot(),
                    action_kind='write',
                )
            )
        return True

    def action_descartar_edicion(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        self._restore_edit_snapshot()
        return True

    @api.model
    def _build_calendar_update_payload(self, before_state=None, after_state=None, action_kind='write'):
        before_state = before_state or {}
        after_state = after_state or {}
        assignment_ids = sorted(set(before_state) | set(after_state))
        changed_dates = sorted({
            state['date']
            for state in [*before_state.values(), *after_state.values()]
            if state.get('date')
        })
        bucket_types = self._sort_calendar_bucket_types({
            state['bucket_type']
            for state in [*before_state.values(), *after_state.values()]
            if state.get('bucket_type')
        })
        if not assignment_ids and not changed_dates and not bucket_types:
            return {}
        return {
            'action_kind': action_kind,
            'assignment_ids': assignment_ids,
            'bucket_types': bucket_types,
            'changed_dates': changed_dates,
        }

    @api.model
    def _send_calendar_update_notification(self, payload):
        if not payload:
            return
        self.env['bus.bus']._sendone(
            PORTALGESTOR_CALENDAR_CHANNEL,
            PORTALGESTOR_CALENDAR_NOTIFICATION,
            payload,
        )

    @api.model
    def get_calendar_bucket_summary(self, date_start, date_end):
        start_date = fields.Date.to_date(date_start)
        end_date = fields.Date.to_date(date_end)
        if not start_date or not end_date:
            return []

        bucket_map = self._get_calendar_bucket_map()
        domain = [
            ('fecha', '>=', start_date),
            ('fecha', '<=', end_date),
            ('confirmado', '=', True),
        ]
        domain += self._get_calendar_owner_filter_domain()
        grouped = self._read_group(
            domain,
            ['fecha:day', 'calendar_bucket_type'],
            ['__count'],
            order='fecha:day ASC, calendar_bucket_type ASC',
        )

        buckets = []
        for fecha, bucket_type, count in grouped:
            bucket_info = bucket_map.get(bucket_type)
            date_value = fields.Date.to_string(fecha)
            if not date_value or not bucket_info or not count:
                continue

            buckets.append({
                'id': f"portalgestor_bucket_{bucket_type}_{date_value}",
                'bucket_type': bucket_type,
                'count': count,
                'date': date_value,
                'label': bucket_info['label'],
                'priority': bucket_info['priority'],
                'title': f"{bucket_info['label']} [{count}]",
            })

        return sorted(buckets, key=lambda bucket: (bucket['date'], bucket['priority']))

    @api.model
    def get_calendar_bucket_records(self, date_value, bucket_type):
        fecha = fields.Date.to_date(date_value)
        bucket_info = self._get_calendar_bucket_map().get(bucket_type)
        if not fecha or not bucket_info:
            return []

        records = self.search(
            [
                ('fecha', '=', fecha),
                ('calendar_bucket_type', '=', bucket_type),
                ('confirmado', '=', True),
            ] + self._get_calendar_owner_filter_domain(),
            order='name, id',
        )
        user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
            records.mapped('usuario_id').ids
        )
        user_types = self.env['usuarios.usuario'].get_portalgestor_user_types(records.mapped('usuario_id').ids)
        return [
            {
                'id': record.id,
                'name': user_view_data.get(record.usuario_id.id, {}).get('display_name')
                or record.usuario_id.display_name
                or record.usuario_id.name
                or record.name,
                'form_title': _("Horario del usuario %s") % (
                    user_view_data.get(record.usuario_id.id, {}).get('display_name')
                    or record.usuario_id.display_name
                    or record.usuario_id.name
                    or record.name
                ),
                'user_type_badge': user_types.get(record.usuario_id.id, {}).get('badge', ''),
                'user_type_label': user_types.get(record.usuario_id.id, {}).get('label', ''),
                'can_edit': user_view_data.get(record.usuario_id.id, {}).get('can_edit', True),
                'gestor_name': record._get_owner_display_name(),
            }
            for record in records
        ]

    @api.model
    def _get_future_calendar_start_date(self, start_date=None):
        return fields.Date.to_date(start_date) or fields.Date.to_date(fields.Date.context_today(self))

    @api.model
    def _normalize_calendar_cutoff_hour(self, start_hour):
        if start_hour is None:
            return None
        return min(max(float(start_hour), 0.0), 24.0)

    @api.model
    def _get_future_calendar_cutoff(self, start_date=None, start_hour=None):
        cutoff_date = fields.Date.to_date(start_date)
        cutoff_hour = self._normalize_calendar_cutoff_hour(start_hour)
        if cutoff_date is not None and cutoff_hour is None:
            return cutoff_date, 0.0

        context_cutoff = self.env.context.get('portalgestor_cutoff_datetime')
        if cutoff_date is None or cutoff_hour is None:
            cutoff_datetime = (
                fields.Datetime.to_datetime(context_cutoff)
                if context_cutoff
                else fields.Datetime.now()
            )
            cutoff_datetime = fields.Datetime.context_timestamp(self, cutoff_datetime)
            if cutoff_date is None:
                cutoff_date = cutoff_datetime.date()
            if cutoff_hour is None:
                cutoff_hour = (
                    cutoff_datetime.hour
                    + cutoff_datetime.minute / 60.0
                    + cutoff_datetime.second / 3600.0
                )
        return cutoff_date, self._normalize_calendar_cutoff_hour(cutoff_hour) or 0.0

    @api.model
    def _mark_fixed_lines_as_manual_exception(self, lineas):
        fixed_lines = lineas.filtered('asignacion_mensual_id')
        if not fixed_lines:
            return fixed_lines

        self.env['portalgestor.asignacion.linea']._ensure_fixed_day_exceptions(
            {
                (linea.asignacion_mensual_id.id, linea.fecha)
                for linea in fixed_lines
                if linea.asignacion_mensual_id and linea.fecha
            },
            'manual',
        )
        fixed_lines.mapped('asignacion_mensual_id')._mark_unconfirmed()
        return fixed_lines

    @api.model
    def release_future_worker_assignments(self, worker_ids, start_date=None, start_hour=None):
        worker_ids = worker_ids.ids if hasattr(worker_ids, 'ids') else worker_ids
        worker_ids = [worker_id for worker_id in worker_ids if worker_id]
        if not worker_ids:
            return self.env['portalgestor.asignacion.linea']

        fecha_inicio, hora_inicio = self._get_future_calendar_cutoff(start_date, start_hour)
        lineas = self.env['portalgestor.asignacion.linea'].search([
            ('trabajador_id', 'in', worker_ids),
            ('fecha', '>=', fecha_inicio),
        ])
        if not lineas:
            return lineas

        lineas_futuras = lineas.filtered(
            lambda linea: linea.fecha > fecha_inicio or linea.hora_inicio >= hora_inicio
        )
        lineas_partidas = lineas.filtered(
            lambda linea: linea.fecha == fecha_inicio and linea.hora_inicio < hora_inicio < linea.hora_fin
        )

        if lineas_futuras:
            lineas_futuras_fijas = lineas_futuras.filtered('asignacion_mensual_linea_id')
            lineas_futuras_individuales = lineas_futuras - lineas_futuras_fijas
            if lineas_futuras_individuales:
                lineas_futuras_individuales.write({'trabajador_id': False})
            if lineas_futuras_fijas:
                lineas_futuras_fijas.mapped('asignacion_mensual_id')._mark_unconfirmed()
                lineas_futuras_fijas.with_context(
                    portalgestor_skip_fixed_exception=True,
                ).write({
                    'trabajador_id': False,
                    'asignacion_mensual_id': False,
                    'asignacion_mensual_linea_id': False,
                })

        if lineas_partidas:
            self._mark_fixed_lines_as_manual_exception(lineas_partidas)
            for linea in lineas_partidas.sorted(key=lambda item: (item.fecha, item.hora_inicio, item.id)):
                original_end = linea.hora_fin
                write_vals = {'hora_fin': hora_inicio}
                if linea.asignacion_mensual_linea_id:
                    write_vals.update({
                        'asignacion_mensual_id': False,
                        'asignacion_mensual_linea_id': False,
                    })
                linea.with_context(
                    portalgestor_skip_fixed_exception=True,
                ).write(write_vals)
                if hora_inicio < original_end:
                    self.env['portalgestor.asignacion.linea'].with_context(
                        portalgestor_skip_fixed_exception=True,
                    ).create({
                        'asignacion_id': linea.asignacion_id.id,
                        'hora_inicio': hora_inicio,
                        'hora_fin': original_end,
                        'trabajador_id': False,
                    })
        return lineas

    @api.model
    def cancel_future_user_assignments(self, usuario_ids, start_date=None, start_hour=None):
        usuario_ids = usuario_ids.ids if hasattr(usuario_ids, 'ids') else usuario_ids
        usuario_ids = [usuario_id for usuario_id in usuario_ids if usuario_id]
        if not usuario_ids:
            return self

        fecha_inicio, hora_inicio = self._get_future_calendar_cutoff(start_date, start_hour)
        asignaciones = self.search([
            ('usuario_id', 'in', usuario_ids),
            ('fecha', '>=', fecha_inicio),
        ])
        if not asignaciones:
            return asignaciones

        asignaciones_hoy = asignaciones.filtered(lambda asignacion: asignacion.fecha == fecha_inicio)
        asignaciones_futuras = asignaciones.filtered(lambda asignacion: asignacion.fecha > fecha_inicio)
        if asignaciones_futuras:
            asignaciones_futuras.with_context(
                portalgestor_skip_fixed_exception=True,
            ).unlink()

        for asignacion in asignaciones_hoy.exists():
            lineas_futuras = asignacion.lineas_ids.filtered(lambda linea: linea.hora_inicio >= hora_inicio)
            lineas_partidas = asignacion.lineas_ids.filtered(
                lambda linea: linea.hora_inicio < hora_inicio < linea.hora_fin
            )
            self._mark_fixed_lines_as_manual_exception(lineas_partidas)
            if lineas_futuras:
                lineas_futuras.filtered('asignacion_mensual_id').mapped('asignacion_mensual_id')._mark_unconfirmed()
                lineas_futuras.with_context(
                    portalgestor_skip_fixed_exception=True,
                ).unlink()
            for linea in lineas_partidas.sorted(key=lambda item: (item.hora_inicio, item.id)):
                write_vals = {'hora_fin': hora_inicio}
                if linea.asignacion_mensual_linea_id:
                    write_vals.update({
                        'asignacion_mensual_id': False,
                        'asignacion_mensual_linea_id': False,
                    })
                linea.with_context(
                    portalgestor_skip_fixed_exception=True,
                ).write(write_vals)
            asignacion.cleanup_empty_assignments()
        return asignaciones

    def cleanup_empty_assignments(self):
        empty_assignments = self.search([
            ('id', 'in', self.ids),
            ('lineas_ids', '=', False),
        ])
        if empty_assignments:
            empty_assignments.with_context(
                portalgestor_skip_calendar_notify=self.env.context.get('portalgestor_skip_calendar_notify')
            ).unlink()
        return empty_assignments

    @api.model_create_multi
    def create(self, vals_list):
        usuario_ids = [vals.get('usuario_id') for vals in vals_list if vals.get('usuario_id')]
        if usuario_ids:
            self._ensure_current_user_can_manage_users(
                self.env['usuarios.usuario'].browse(usuario_ids).exists()
            )
        if self.env.context.get('portalgestor_skip_calendar_notify'):
            return super().create(vals_list)

        records = super(Asignacion, self.with_context(portalgestor_skip_calendar_notify=True)).create(vals_list)
        self._send_calendar_update_notification(
            self._build_calendar_update_payload(
                after_state=records._get_calendar_realtime_snapshot(),
                action_kind='create',
            )
        )
        return records.with_env(self.env)

    def write(self, vals):
        target_users = self.mapped('usuario_id')
        if vals.get('usuario_id'):
            target_users |= self.env['usuarios.usuario'].browse(vals['usuario_id']).exists()
        self._ensure_current_user_can_manage_users(target_users)
        if vals.get('confirmado') is True:
            vals = dict(vals, edit_session_pending=False, edit_snapshot_data=False)
        if self.env.context.get('portalgestor_skip_calendar_notify'):
            return super().write(vals)

        before_state = self._get_calendar_realtime_snapshot()
        monthly_ids_by_assignment = {}
        if 'lineas_ids' in vals:
            monthly_ids_by_assignment = self.env['portalgestor.asignacion.linea']._get_assignment_fixed_monthly_ids(self)
        result = super(Asignacion, self.with_context(portalgestor_skip_calendar_notify=True)).write(vals)
        if monthly_ids_by_assignment:
            line_model = self.env['portalgestor.asignacion.linea']
            line_model._merge_assignment_fixed_monthly_ids(monthly_ids_by_assignment, self)
            line_model._detach_fixed_days_when_worker_changed(self, monthly_ids_by_assignment)
            self.with_context(portalgestor_skip_calendar_notify=True).cleanup_empty_assignments()
        self._send_calendar_update_notification(
            self._build_calendar_update_payload(
                before_state=before_state,
                after_state=self.exists()._get_calendar_realtime_snapshot(),
                action_kind='write',
            )
        )
        return result

    def unlink(self):
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        if self.env.context.get('portalgestor_skip_calendar_notify'):
            return super().unlink()

        before_state = self._get_calendar_realtime_snapshot()
        result = super(Asignacion, self.with_context(portalgestor_skip_calendar_notify=True)).unlink()
        self._send_calendar_update_notification(
            self._build_calendar_update_payload(
                before_state=before_state,
                action_kind='unlink',
            )
        )
        return result

    def _get_verification_action(self, asignacion_mensual_id=False):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))

        lineas_con_trabajador = self._run_verification_checks()
        if not lineas_con_trabajador:
            return True

        otras_lineas = self.env['portalgestor.asignacion.linea'].search(
            [
                ('trabajador_id', 'in', lineas_con_trabajador.mapped('trabajador_id').ids),
                ('fecha', '=', self.fecha),
                ('asignacion_id', '!=', self.id),
            ],
            order='trabajador_id, hora_inicio, hora_fin, id',
        )
        otras_lineas_por_trabajador = defaultdict(list)
        for otra_linea in otras_lineas:
            otras_lineas_por_trabajador[otra_linea.trabajador_id.id].append(otra_linea)
        user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
            otras_lineas.mapped('asignacion_id.usuario_id').ids
        )

        for linea in lineas_con_trabajador:
            for conflicto in otras_lineas_por_trabajador.get(linea.trabajador_id.id, []):
                overlap = min(linea.hora_fin, conflicto.hora_fin) - max(
                    linea.hora_inicio, conflicto.hora_inicio
                )
                if overlap > 0:
                    if not self.env.user._can_manage_target_group(conflicto.asignacion_id.usuario_id.grupo):
                        return self._launch_wizard(
                            'protected_intecum_overlapping',
                            linea.id,
                            conflicto.id,
                            asignacion_mensual_id=asignacion_mensual_id,
                        )
                    return self._launch_wizard(
                        'overlapping',
                        linea.id,
                        conflicto.id,
                        asignacion_mensual_id=asignacion_mensual_id,
                    )

        avisos = []
        avisos_set = set()
        for linea in lineas_con_trabajador:
            for otra in otras_lineas_por_trabajador.get(linea.trabajador_id.id, []):
                usuario_conflicto = (
                    user_view_data.get(otra.asignacion_id.usuario_id.id, {}).get('display_name')
                    or otra.asignacion_id.usuario_id.display_name
                )
                aviso = (
                    f"- {linea.trabajador_id.name}: ya asignado a "
                    f"{usuario_conflicto} de "
                    f"{self._format_hora(otra.hora_inicio)} a {self._format_hora(otra.hora_fin)}"
                )
                if aviso not in avisos_set:
                    avisos_set.add(aviso)
                    avisos.append(aviso)

        if avisos:
            return self._launch_info_wizard(
                "\n".join(avisos),
                asignacion_mensual_id=asignacion_mensual_id,
            )

        return True

    def action_verificar_y_confirmar(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        result = self._get_verification_action()
        if isinstance(result, dict):
            return result
        return self._apply_confirmation_as_current_manager()

    def _run_verification_checks(self):
        self.ensure_one()
        if self.usuario_id.baja:
            raise ValidationError(_("No puedes confirmar un horario para un usuario dado de baja."))
        if not self.usuario_id.has_ap_service:
            raise ValidationError(_("Solo puedes confirmar horarios para usuarios con el servicio AP activo."))

        lineas_con_trabajador = self.lineas_ids.filtered('trabajador_id').sorted(
            key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id)
        )
        if not lineas_con_trabajador:
            return lineas_con_trabajador

        vacaciones = self.env['trabajadores.vacacion'].search([
            ('trabajador_id', 'in', lineas_con_trabajador.mapped('trabajador_id').ids),
            ('date_start', '<=', self.fecha),
            ('date_stop', '>=', self.fecha),
        ])
        vacaciones_por_trabajador = {vacacion.trabajador_id.id: vacacion for vacacion in vacaciones}
        target_zone = self.usuario_id.zona_trabajo_id
        lineas_por_trabajador = defaultdict(list)

        for linea in lineas_con_trabajador:
            trabajador = linea.trabajador_id
            lineas_por_trabajador[trabajador.id].append(linea)
            if trabajador.baja:
                raise ValidationError(
                    _("El AP %(worker)s esta dado de baja y no se puede confirmar en %(date)s.")
                    % {
                        'worker': trabajador.display_name or trabajador.name,
                        'date': fields.Date.to_string(self.fecha),
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
            vacacion = vacaciones_por_trabajador.get(trabajador.id)
            if vacacion:
                raise ValidationError(
                    _("El AP %(worker)s tiene vacaciones el dia %(date)s y no se puede confirmar este horario.")
                    % {
                        'worker': trabajador.display_name or trabajador.name,
                        'date': fields.Date.to_string(self.fecha),
                    }
                )

        for trabajador_id, worker_lines in lineas_por_trabajador.items():
            ordered_lines = sorted(worker_lines, key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id))
            previous_line = False
            for linea in ordered_lines:
                if previous_line and linea.hora_inicio < previous_line.hora_fin:
                    trabajador = linea.trabajador_id or previous_line.trabajador_id
                    raise ValidationError(
                        _("El AP %(worker)s tiene dos tramos solapados dentro del mismo horario.")
                        % {
                            'worker': trabajador.display_name or trabajador.name,
                        }
                    )
                previous_line = linea

        return lineas_con_trabajador

    def _launch_info_wizard(self, resumen, asignacion_mensual_id=False):
        wizard = self.env['portalgestor.conflict.wizard'].create({
            'asignacion_id': self.id,
            'asignacion_mensual_id': asignacion_mensual_id,
            'conflict_type': 'info_same_day',
            'info_resumen': resumen,
        })
        return {
            'name': 'Aviso de Asignaciones del Mismo Dia',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.conflict.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_editar(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        if self.confirmado and not self.edit_session_pending:
            self._set_edit_snapshot()
        self.confirmado = False
        return True

    def action_eliminar_horario(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        self.unlink()
        return {'type': 'ir.actions.act_window_close'}

    def _launch_wizard(self, conflict_type, linea_actual_id, linea_conflicto_id, asignacion_mensual_id=False):
        wizard = self.env['portalgestor.conflict.wizard'].create({
            'asignacion_id': self.id,
            'asignacion_mensual_id': asignacion_mensual_id,
            'conflict_type': conflict_type,
            'linea_actual_id': linea_actual_id,
            'linea_conflicto_id': linea_conflicto_id,
        })
        return {
            'name': 'Conflicto de Horario',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.conflict.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def name_get(self):
        user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
            self.mapped('usuario_id').ids
        )
        return [
            (
                record.id,
                user_view_data.get(record.usuario_id.id, {}).get('display_name')
                or record.usuario_id.display_name
                or record.name,
            )
            for record in self
        ]


class AsignacionLinea(models.Model):
    _name = 'portalgestor.asignacion.linea'
    _description = 'Linea de Asignacion'

    asignacion_id = fields.Many2one('portalgestor.asignacion', ondelete='cascade', index=True)
    hora_inicio = fields.Float(string='Hora Inicio', required=True)
    hora_fin = fields.Float(string='Hora Fin', required=True)
    trabajador_id = fields.Many2one('trabajadores.trabajador', string='AP', index=True)
    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Trabajo fijo',
        ondelete='set null',
        index=True,
    )
    asignacion_mensual_linea_id = fields.Many2one(
        'portalgestor.asignacion.mensual.linea',
        string='Tramo de trabajo fijo',
        ondelete='set null',
        index=True,
    )
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        related='asignacion_id.usuario_id.zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    fecha = fields.Date(related='asignacion_id.fecha', string='Fecha', store=True, index=True)
    gestor_owner_id = fields.Many2one(
        'res.users',
        related='asignacion_id.gestor_owner_id',
        string='Gestor propietario',
        store=True,
        readonly=True,
        index=True,
    )

    def _ensure_current_user_can_manage_parent_assignments(self, assignments):
        self.env['portalgestor.asignacion']._ensure_current_user_can_manage_users(
            assignments.mapped('usuario_id')
        )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_trab_fecha_idx',
            tablename=self._table,
            expressions=['trabajador_id', 'fecha'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_mensual_fecha_idx',
            tablename=self._table,
            expressions=['asignacion_mensual_id', 'fecha'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_mensual_linea_fecha_idx',
            tablename=self._table,
            expressions=['asignacion_mensual_linea_id', 'fecha'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_owner_fecha_idx',
            tablename=self._table,
            expressions=['gestor_owner_id', 'fecha'],
        )
        self.env.cr.execute(
            """
                UPDATE portalgestor_asignacion_linea linea
                   SET gestor_owner_id = asignacion.gestor_owner_id
                  FROM portalgestor_asignacion asignacion
                 WHERE asignacion.id = linea.asignacion_id
                   AND linea.gestor_owner_id IS DISTINCT FROM asignacion.gestor_owner_id
            """
        )

    def _get_impacted_calendar_assignments(self, vals_list=None):
        assignment_ids = set(self.mapped('asignacion_id').ids)
        for vals in vals_list or []:
            assignment_id = vals.get('asignacion_id')
            if assignment_id:
                assignment_ids.add(assignment_id)
        return self.env['portalgestor.asignacion'].browse(sorted(assignment_ids))

    def _get_assignment_fixed_monthly_ids(self, assignments):
        monthly_ids_by_assignment = {}
        for assignment in assignments.exists():
            monthly_ids = set(
                assignment.lineas_ids.filtered('asignacion_mensual_id').mapped('asignacion_mensual_id').ids
            )
            if monthly_ids:
                monthly_ids_by_assignment[assignment.id] = monthly_ids
        return monthly_ids_by_assignment

    def _merge_assignment_fixed_monthly_ids(self, monthly_ids_by_assignment, assignments):
        for assignment in assignments.exists():
            if assignment.id not in monthly_ids_by_assignment:
                monthly_ids_by_assignment[assignment.id] = set()
            monthly_ids_by_assignment[assignment.id].update(
                assignment.lineas_ids.filtered('asignacion_mensual_id').mapped('asignacion_mensual_id').ids
            )
        return monthly_ids_by_assignment

    def _ensure_fixed_day_exceptions(self, monthly_date_pairs, exception_type='manual'):
        Exception = self.env['portalgestor.asignacion.mensual.excepcion']
        if not monthly_date_pairs:
            return Exception

        monthly_ids = sorted({monthly_id for monthly_id, __date in monthly_date_pairs})
        dates = sorted({date_value for __monthly_id, date_value in monthly_date_pairs})
        existing_exceptions = Exception.search([
            ('asignacion_mensual_id', 'in', monthly_ids),
            ('fecha', 'in', dates),
        ])
        exceptions_by_key = {
            (exception.asignacion_mensual_id.id, exception.fecha): exception
            for exception in existing_exceptions
            if exception.asignacion_mensual_id and exception.fecha
        }

        created_exceptions = Exception.browse()
        for monthly_id, date_value in monthly_date_pairs:
            exception_key = (monthly_id, date_value)
            existing_exception = exceptions_by_key.get(exception_key)
            if existing_exception:
                if existing_exception.tipo != exception_type:
                    existing_exception.write({'tipo': exception_type})
                created_exceptions |= existing_exception
                continue

            created_exception = Exception.create({
                'asignacion_mensual_id': monthly_id,
                'fecha': date_value,
                'tipo': exception_type,
            })
            exceptions_by_key[exception_key] = created_exception
            created_exceptions |= created_exception

        return created_exceptions

    def _detach_fixed_days_when_worker_changed(self, assignments, monthly_ids_by_assignment):
        if (
            self.env.context.get('portalgestor_skip_fixed_sync')
            or self.env.context.get('portalgestor_skip_fixed_exception')
        ):
            return self.browse()

        FixedAssignment = self.env['portalgestor.asignacion.mensual']
        existing_exceptions = self.env['portalgestor.asignacion.mensual.excepcion'].search([
            ('asignacion_mensual_id', 'in', sorted({
                monthly_id
                for monthly_ids in monthly_ids_by_assignment.values()
                for monthly_id in monthly_ids
            })),
            ('fecha', 'in', assignments.mapped('fecha')),
        ]) if monthly_ids_by_assignment else self.env['portalgestor.asignacion.mensual.excepcion']
        existing_exception_keys = {
            (exception.asignacion_mensual_id.id, exception.fecha)
            for exception in existing_exceptions
            if exception.asignacion_mensual_id and exception.fecha
        }

        lines_to_detach = self.browse()
        exception_pairs = set()
        for assignment in assignments.exists():
            manual_worker_ids = sorted(
                line.trabajador_id.id
                for line in assignment.lineas_ids
                if not line.asignacion_mensual_id and line.trabajador_id
            )
            for monthly_id in monthly_ids_by_assignment.get(assignment.id, set()):
                if (monthly_id, assignment.fecha) in existing_exception_keys:
                    continue

                monthly = FixedAssignment.browse(monthly_id).exists()
                if not monthly:
                    continue
                if monthly.usuario_id != assignment.usuario_id:
                    continue
                if assignment.fecha < monthly.fecha_inicio or assignment.fecha > monthly.fecha_fin:
                    continue

                fixed_lines = assignment.lineas_ids.filtered(
                    lambda line: line.asignacion_mensual_id.id == monthly.id
                )
                current_worker_signature = sorted(
                    [line.trabajador_id.id for line in fixed_lines if line.trabajador_id] + manual_worker_ids
                )
                fixed_worker_signature = sorted(monthly.linea_fija_ids.mapped('trabajador_id').ids)
                if current_worker_signature == fixed_worker_signature:
                    continue

                exception_pairs.add((monthly.id, assignment.fecha))
                lines_to_detach |= fixed_lines

        if exception_pairs:
            self._ensure_fixed_day_exceptions(exception_pairs, 'manual')
            self.env['portalgestor.asignacion.mensual'].browse(
                sorted({monthly_id for monthly_id, __date in exception_pairs})
            )._mark_unconfirmed()
        if lines_to_detach:
            lines_to_detach.with_context(
                portalgestor_skip_calendar_notify=True,
                portalgestor_skip_fixed_exception=True,
            ).write({
                'asignacion_mensual_id': False,
                'asignacion_mensual_linea_id': False,
            })
        return lines_to_detach

    @api.model_create_multi
    def create(self, vals_list):
        assignment_ids = [vals.get('asignacion_id') for vals in vals_list if vals.get('asignacion_id')]
        if assignment_ids:
            self._ensure_current_user_can_manage_parent_assignments(
                self.env['portalgestor.asignacion'].browse(assignment_ids).exists()
            )
        if self.env.context.get('portalgestor_skip_calendar_notify'):
            return super().create(vals_list)

        impacted_assignments = self._get_impacted_calendar_assignments(vals_list)
        before_state = impacted_assignments._get_calendar_realtime_snapshot()
        monthly_ids_by_assignment = self._get_assignment_fixed_monthly_ids(impacted_assignments)
        records = super().create(vals_list)
        after_assignments = impacted_assignments | records.mapped('asignacion_id')
        self._merge_assignment_fixed_monthly_ids(monthly_ids_by_assignment, after_assignments)
        records._detach_fixed_days_when_worker_changed(after_assignments, monthly_ids_by_assignment)
        after_state = after_assignments._get_calendar_realtime_snapshot()
        after_assignments._send_calendar_update_notification(
            self.env['portalgestor.asignacion']._build_calendar_update_payload(
                before_state=before_state,
                after_state=after_state,
                action_kind='create',
            )
        )
        return records

    def write(self, vals):
        impacted_assignments_for_security = self.mapped('asignacion_id')
        if vals.get('asignacion_id'):
            impacted_assignments_for_security |= self.env['portalgestor.asignacion'].browse(vals['asignacion_id']).exists()
        self._ensure_current_user_can_manage_parent_assignments(impacted_assignments_for_security)
        if self.env.context.get('portalgestor_skip_calendar_notify'):
            return super().write(vals)

        impacted_assignments = self._get_impacted_calendar_assignments([vals])
        before_state = impacted_assignments._get_calendar_realtime_snapshot()
        monthly_ids_by_assignment = self._get_assignment_fixed_monthly_ids(impacted_assignments | self.mapped('asignacion_id'))
        result = super(
            AsignacionLinea,
            self.with_context(portalgestor_skip_calendar_notify=True),
        ).write(vals)
        after_assignments = impacted_assignments | self.mapped('asignacion_id')
        self._merge_assignment_fixed_monthly_ids(monthly_ids_by_assignment, after_assignments)
        self._detach_fixed_days_when_worker_changed(after_assignments, monthly_ids_by_assignment)
        after_state = after_assignments._get_calendar_realtime_snapshot()
        after_assignments._send_calendar_update_notification(
            self.env['portalgestor.asignacion']._build_calendar_update_payload(
                before_state=before_state,
                after_state=after_state,
                action_kind='write',
            )
        )
        return result

    def unlink(self):
        self._ensure_current_user_can_manage_parent_assignments(self.mapped('asignacion_id'))
        if self.env.context.get('portalgestor_skip_calendar_notify'):
            return super().unlink()

        impacted_assignments = self.mapped('asignacion_id')
        before_state = impacted_assignments._get_calendar_realtime_snapshot()
        monthly_ids_by_assignment = self._get_assignment_fixed_monthly_ids(impacted_assignments)
        result = super(
            AsignacionLinea,
            self.with_context(portalgestor_skip_calendar_notify=True),
        ).unlink()
        self.env['portalgestor.asignacion.linea']._detach_fixed_days_when_worker_changed(
            impacted_assignments,
            monthly_ids_by_assignment,
        )
        impacted_assignments.with_context(
            portalgestor_skip_calendar_notify=True
        ).cleanup_empty_assignments()
        after_state = impacted_assignments.exists()._get_calendar_realtime_snapshot()
        impacted_assignments._send_calendar_update_notification(
            self.env['portalgestor.asignacion']._build_calendar_update_payload(
                before_state=before_state,
                after_state=after_state,
                action_kind='unlink',
            )
        )
        return result

    @api.constrains('hora_inicio', 'hora_fin')
    def _check_horas(self):
        for record in self:
            if record.hora_inicio < 0 or record.hora_inicio >= 24:
                raise ValidationError("La hora de inicio debe estar entre 00:00 y 23:59.")
            if record.hora_fin < 0 or record.hora_fin >= 24:
                raise ValidationError("La hora de fin debe estar entre 00:00 y 23:59.")
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError("La hora de inicio debe ser anterior a la hora de fin.")
