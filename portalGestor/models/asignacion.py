# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
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
    trabajador_calendar_filter_id = fields.Many2one(
        'trabajadores.trabajador',
        string='Trabajador',
        compute='_compute_calendar_worker_fields',
        search='_search_trabajador_calendar_filter_id',
    )
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='Trabajador',
        compute='_compute_calendar_worker_fields',
        search='_search_trabajador_calendar_filter_id',
    )
    trabajador_resumen = fields.Char(
        string='Cuidador',
        compute='_compute_lineas_resumen',
        store=True,
    )
    rango_horas_resumen = fields.Char(
        string='Rango de horas',
        compute='_compute_lineas_resumen',
        store=True,
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

    @api.depends('usuario_id.name', 'fecha')
    def _compute_name(self):
        for record in self:
            if record.usuario_id and record.fecha:
                record.name = record.usuario_id.name
            else:
                record.name = _("Nueva Asignacion")

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

    @staticmethod
    def _format_hora(hour_float):
        return '%02d:%02d' % (int(hour_float), int((hour_float % 1) * 60))

    def _get_calendar_bucket_type(self):
        self.ensure_one()
        return self.calendar_bucket_type or self._calculate_calendar_bucket_type(self.lineas_ids)

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
        for record in self.exists():
            snapshot[record.id] = {
                'date': fields.Date.to_string(record.fecha),
                'bucket_type': record._get_calendar_bucket_type(),
            }
        return snapshot

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
        grouped = self._read_group(
            [
                ('fecha', '>=', start_date),
                ('fecha', '<=', end_date),
            ],
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
            ],
            order='name, id',
        )
        return [
            {
                'id': record.id,
                'name': record.usuario_id.name or record.name,
            }
            for record in records
        ]

    @api.model
    def _get_future_calendar_start_date(self, start_date=None):
        return fields.Date.to_date(start_date) or fields.Date.to_date(fields.Date.context_today(self))

    @api.model
    def release_future_worker_assignments(self, worker_ids, start_date=None):
        worker_ids = worker_ids.ids if hasattr(worker_ids, 'ids') else worker_ids
        worker_ids = [worker_id for worker_id in worker_ids if worker_id]
        if not worker_ids:
            return self.env['portalgestor.asignacion.linea']

        fecha_inicio = self._get_future_calendar_start_date(start_date)
        lineas = self.env['portalgestor.asignacion.linea'].search([
            ('trabajador_id', 'in', worker_ids),
            ('fecha', '>=', fecha_inicio),
        ])
        if not lineas:
            return lineas

        lineas_fijas = lineas.filtered('asignacion_mensual_linea_id')
        lineas_individuales = lineas - lineas_fijas
        if lineas_individuales:
            lineas_individuales.write({'trabajador_id': False})
        if lineas_fijas:
            lineas_fijas.with_context(
                portalgestor_skip_fixed_exception=True,
            ).write({
                'trabajador_id': False,
                'asignacion_mensual_id': False,
                'asignacion_mensual_linea_id': False,
            })
        return lineas

    @api.model
    def cancel_future_user_assignments(self, usuario_ids, start_date=None):
        usuario_ids = usuario_ids.ids if hasattr(usuario_ids, 'ids') else usuario_ids
        usuario_ids = [usuario_id for usuario_id in usuario_ids if usuario_id]
        if not usuario_ids:
            return self

        fecha_inicio = self._get_future_calendar_start_date(start_date)
        asignaciones = self.search([
            ('usuario_id', 'in', usuario_ids),
            ('fecha', '>=', fecha_inicio),
        ])
        if asignaciones:
            asignaciones.with_context(
                portalgestor_skip_fixed_exception=True,
            ).unlink()
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

        lineas_con_trabajador = self.lineas_ids.filtered('trabajador_id').sorted(
            key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id)
        )
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

        for linea in lineas_con_trabajador:
            for conflicto in otras_lineas_por_trabajador.get(linea.trabajador_id.id, []):
                overlap = min(linea.hora_fin, conflicto.hora_fin) - max(
                    linea.hora_inicio, conflicto.hora_inicio
                )
                if overlap > 0:
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
                aviso = (
                    f"- {linea.trabajador_id.name}: ya asignado a "
                    f"{otra.asignacion_id.usuario_id.name} de "
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
        result = self._get_verification_action()
        if isinstance(result, dict):
            return result
        self.confirmado = True
        return True

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
        self.confirmado = False
        return True

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


class AsignacionLinea(models.Model):
    _name = 'portalgestor.asignacion.linea'
    _description = 'Linea de Asignacion'

    asignacion_id = fields.Many2one('portalgestor.asignacion', ondelete='cascade', index=True)
    hora_inicio = fields.Float(string='Hora Inicio', required=True)
    hora_fin = fields.Float(string='Hora Fin', required=True)
    trabajador_id = fields.Many2one('trabajadores.trabajador', string='Trabajador', index=True)
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
