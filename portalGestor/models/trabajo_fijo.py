# -*- coding: utf-8 -*-
import calendar
import json
from collections import defaultdict
from datetime import timedelta

from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
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


class TrabajoFijo(models.Model):
    _name = 'portalgestor.trabajo_fijo'
    _description = 'Trabajo Fijo Mensual'
    _order = 'year desc, month desc, usuario_id, id desc'

    _sql_constraints = [
        (
            'unique_usuario_month_year',
            'unique(usuario_id, month, year)',
            'Ya existe un trabajo fijo para este usuario en este mes.',
        ),
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
    usuario_localidad_id = fields.Many2one(
        related='usuario_id.localidad_id',
        string='Localidad del Usuario',
        readonly=True,
    )
    usuario_zona_trabajo_id = fields.Many2one(
        related='usuario_id.zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    month = fields.Selection(
        selection=MONTH_SELECTION,
        string='Mes',
        required=True,
        default=lambda self: str(fields.Date.context_today(self).month),
        index=True,
    )
    year = fields.Integer(
        string='Ano',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
        index=True,
    )
    fecha_inicio = fields.Date(string='Inicio mes', required=True, index=True)
    fecha_fin = fields.Date(string='Fin mes', required=True, index=True)
    line_ids = fields.One2many(
        'portalgestor.trabajo_fijo.linea',
        'trabajo_fijo_id',
        string='Tramos del mes',
        copy=True,
    )
    asignacion_linea_ids = fields.One2many(
        'portalgestor.asignacion.linea',
        'trabajo_fijo_id',
        string='Asignaciones generadas',
        readonly=True,
    )
    confirmado = fields.Boolean(string='Horario Confirmado', default=False, copy=False)
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
    manager_edit_blocked = fields.Boolean(
        string='Edicion bloqueada para el gestor actual',
        compute='_compute_manager_edit_blocked',
    )
    content_locked = fields.Boolean(
        string='Contenido bloqueado',
        compute='_compute_locks',
    )
    header_locked = fields.Boolean(
        string='Cabecera bloqueada',
        compute='_compute_locks',
    )
    template_day_count = fields.Integer(
        string='Dias con horario',
        compute='_compute_totals',
    )
    template_line_count = fields.Integer(
        string='Tramos en plantilla',
        compute='_compute_totals',
    )
    total_dias_generados = fields.Integer(
        string='Dias generados',
        compute='_compute_totals',
    )
    total_lineas_generadas = fields.Integer(
        string='Lineas generadas',
        compute='_compute_totals',
    )
    month_grid_html = fields.Html(
        string='Resumen mensual',
        compute='_compute_month_grid_html',
        sanitize=False,
    )
    legacy_asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Trabajo fijo legacy',
        ondelete='set null',
        copy=False,
        index=True,
    )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_trabajo_fijo_owner_fecha_idx',
            tablename=self._table,
            expressions=['gestor_owner_id', 'year desc', 'month desc', 'id desc'],
        )
        self.env.cr.execute(
            f"""
                UPDATE {self._table}
                   SET gestor_owner_id = COALESCE(write_uid, create_uid)
                 WHERE gestor_owner_id IS NULL
            """
        )

    @staticmethod
    def _format_hora(hour_float):
        hour = int(hour_float or 0)
        minute = int(round(((hour_float or 0.0) - hour) * 60))
        if minute >= 60:
            hour += 1
            minute -= 60
        return '%02d:%02d' % (hour, minute)

    @staticmethod
    def _get_month_bounds(month_value, year_value):
        month_number = int(month_value)
        year_number = int(year_value)
        month_start = fields.Date.to_date(f"{year_number:04d}-{month_number:02d}-01")
        month_end = month_start + timedelta(days=calendar.monthrange(year_number, month_number)[1] - 1)
        return month_start, month_end

    @staticmethod
    def _get_week_dates(month_value, year_value):
        return calendar.Calendar(firstweekday=0).monthdatescalendar(int(year_value), int(month_value))

    @api.depends('usuario_id.display_name', 'usuario_id.name', 'month', 'year', 'line_ids')
    def _compute_name(self):
        for record in self:
            if not record.usuario_id or not record.month or not record.year:
                record.name = _('Nuevo Trabajo Fijo')
                continue
            record.name = _('%(usuario)s | %(mes)s %(ano)s (%(tramos)s tramos)') % {
                'usuario': record.usuario_id.display_name or record.usuario_id.name,
                'mes': MONTH_LABELS.get(record.month, ''),
                'ano': record.year,
                'tramos': len(record.line_ids),
            }

    @api.depends('gestor_owner_id')
    def _compute_gestor_owner_label(self):
        for record in self:
            record.gestor_owner_label = (
                record.gestor_owner_id.display_name
                or record.gestor_owner_id.name
                or _('Sin gestor')
            )

    @api.depends('usuario_grupo')
    def _compute_manager_edit_blocked(self):
        for record in self:
            record.manager_edit_blocked = not self.env.user._can_manage_target_group(record.usuario_grupo)

    @api.depends('confirmado', 'edit_session_pending', 'manager_edit_blocked')
    def _compute_locks(self):
        for record in self:
            record.header_locked = bool(record.manager_edit_blocked or record.confirmado)
            record.content_locked = bool(
                record.manager_edit_blocked or (record.confirmado and not record.edit_session_pending)
            )

    @api.depends('line_ids.fecha', 'asignacion_linea_ids.fecha')
    def _compute_totals(self):
        for record in self:
            template_dates = {date_value for date_value in record.line_ids.mapped('fecha') if date_value}
            generated_dates = {date_value for date_value in record.asignacion_linea_ids.mapped('fecha') if date_value}
            record.template_day_count = len(template_dates)
            record.template_line_count = len(record.line_ids)
            record.total_dias_generados = len(generated_dates)
            record.total_lineas_generadas = len(record.asignacion_linea_ids)

    @api.depends(
        'month',
        'year',
        'line_ids.fecha',
        'line_ids.hora_inicio',
        'line_ids.hora_fin',
        'line_ids.trabajador_id',
    )
    def _compute_month_grid_html(self):
        for record in self:
            if not record.month or not record.year:
                record.month_grid_html = ''
                continue
            record_id = record.id if isinstance(record.id, int) else False
            lines_by_date = defaultdict(list)
            for line in record.line_ids.sorted(key=lambda item: (item.fecha, item.hora_inicio, item.hora_fin, item.id)):
                if line.fecha:
                    lines_by_date[line.fecha].append(line)

            rows = []
            for week_number, week_dates in enumerate(self._get_week_dates(record.month, record.year), start=1):
                cells = []
                for date_value in week_dates:
                    if date_value.month != int(record.month):
                        cells.append('<td class="o_portalgestor_fixed_grid_cell o_portalgestor_fixed_grid_out"></td>')
                        continue
                    day_lines = lines_by_date.get(date_value, [])
                    if day_lines:
                        chunks = []
                        for line in day_lines[:3]:
                            worker = escape(line.trabajador_id.display_name or line.trabajador_id.name or '')
                            chunks.append(
                                '<div class="o_portalgestor_fixed_grid_line">'
                                f'{escape(self._format_hora(line.hora_inicio))}-{escape(self._format_hora(line.hora_fin))} {worker}'
                                '</div>'
                            )
                        if len(day_lines) > 3:
                            chunks.append(
                                '<div class="o_portalgestor_fixed_grid_more">'
                                f'+{len(day_lines) - 3} tramos'
                                '</div>'
                            )
                        line_html = ''.join(chunks)
                    else:
                        line_html = '<div class="o_portalgestor_fixed_grid_empty">Sin tramos</div>'
                    date_string = fields.Date.to_string(date_value)
                    if record_id:
                        cell_content = (
                            '<a href="#" class="o_portalgestor_fixed_grid_day_link" '
                            f'data-trabajo-fijo-id="{record_id}" '
                            f'data-date="{escape(date_string)}" '
                            f'title="{escape(_("Abrir tramos del dia"))}">'
                            f'<div class="o_portalgestor_fixed_grid_day">{date_value.day}</div>{line_html}'
                            '</a>'
                        )
                    else:
                        cell_content = (
                            f'<div class="o_portalgestor_fixed_grid_day">{date_value.day}</div>{line_html}'
                        )
                    cells.append(
                        '<td class="o_portalgestor_fixed_grid_cell">'
                        f'{cell_content}'
                        '</td>'
                    )
                rows.append(
                    '<tr>'
                    f'<th class="o_portalgestor_fixed_grid_week">S{week_number}</th>'
                    + ''.join(cells)
                    + '</tr>'
                )
            record.month_grid_html = (
                '<table class="o_portalgestor_fixed_grid">'
                '<thead><tr><th></th><th>Lun</th><th>Mar</th><th>Mie</th><th>Jue</th><th>Vie</th><th>Sab</th><th>Dom</th></tr></thead>'
                '<tbody>'
                + ''.join(rows)
                + '</tbody></table>'
            )

    def action_open_day_lines(self, date_value):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        if self.confirmado and not self.edit_session_pending:
            self._set_edit_snapshot()

        target_date = fields.Date.to_date(date_value)
        if not target_date:
            raise ValidationError(_("Debes seleccionar un dia del mes."))
        if target_date < self.fecha_inicio or target_date > self.fecha_fin:
            raise ValidationError(_("El dia seleccionado no pertenece al mes del trabajo fijo."))

        list_view = self.env.ref('portalGestor.portalgestor_trabajo_fijo_linea_day_list')
        form_view = self.env.ref('portalGestor.portalgestor_trabajo_fijo_linea_day_form')
        target_date_string = fields.Date.to_string(target_date)
        return {
            'name': _('Tramos %(date)s') % {'date': target_date_string},
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.trabajo_fijo.linea',
            'view_mode': 'list,form',
            'views': [(list_view.id, 'list'), (form_view.id, 'form')],
            'target': 'new',
            'domain': [
                ('trabajo_fijo_id', '=', self.id),
                ('fecha', '=', target_date_string),
            ],
            'context': {
                'default_trabajo_fijo_id': self.id,
                'default_fecha': target_date_string,
                'portalgestor_force_date': True,
                'portalgestor_worker_selector': True,
                'portalgestor_usuario_zona': self.usuario_zona_trabajo_id.id or False,
                'portalgestor_usuario_localidad': self.usuario_localidad_id.id or False,
            },
        }

    @api.constrains('usuario_id')
    def _check_usuario_has_ap_service(self):
        for record in self:
            if record.usuario_id and not record.usuario_id.has_ap_service:
                raise ValidationError(_("Solo puedes asignar trabajos fijos a usuarios con el servicio AP activo."))

    @api.constrains('month', 'year')
    def _check_month_year(self):
        for record in self:
            if not record.month or not record.year:
                raise ValidationError(_("Debes indicar mes y ano."))
            if record.year < 2000 or record.year > 2100:
                raise ValidationError(_("El ano debe estar entre 2000 y 2100."))

    def _ensure_current_user_can_manage_users(self, users):
        forbidden_users = users.filtered(
            lambda usuario: not self.env.user._can_manage_target_group(usuario.grupo)
        )
        if forbidden_users:
            raise AccessError(
                _("Los gestores Agusto no pueden crear, modificar ni eliminar horarios de usuarios de Intecum.")
            )

    def _prepare_month_vals(self, vals, force=False):
        values = dict(vals)
        if not force and not ({'month', 'year'} & set(values)):
            return values
        month_value = values.get('month')
        year_value = values.get('year')
        if not month_value and self:
            month_value = self[0].month
        if not year_value and self:
            year_value = self[0].year
        if month_value and year_value:
            month_start, month_end = self._get_month_bounds(month_value, year_value)
            values['fecha_inicio'] = month_start
            values['fecha_fin'] = month_end
        return values

    @staticmethod
    def _is_status_only_vals(vals):
        return set(vals).issubset({
            'confirmado',
            'edit_session_pending',
            'edit_snapshot_data',
            'gestor_owner_id',
            'legacy_asignacion_mensual_id',
        })

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        for vals in vals_list:
            values = dict(vals)
            today = fields.Date.context_today(self)
            values.setdefault('month', str(today.month))
            values.setdefault('year', today.year)
            values = self._prepare_month_vals(values, force=True)
            user = self.env['usuarios.usuario'].browse(values.get('usuario_id')).exists()
            if user:
                self._ensure_current_user_can_manage_users(user)
            values.setdefault('confirmado', False)
            prepared_vals.append(values)
        return super().create(prepared_vals)

    def write(self, vals):
        values = self._prepare_month_vals(vals)
        target_users = self.mapped('usuario_id')
        if values.get('usuario_id'):
            target_users |= self.env['usuarios.usuario'].browse(values['usuario_id']).exists()
        self._ensure_current_user_can_manage_users(target_users)

        if (
            not self.env.context.get('portalgestor_skip_trabajo_fijo_edit_check')
            and not self._is_status_only_vals(values)
            and any(record.confirmado and not record.edit_session_pending for record in self)
        ):
            raise ValidationError(_("Pulsa Modificar Horario antes de cambiar un trabajo fijo confirmado."))
        if {'month', 'year'} & set(values):
            records_with_lines = self.filtered('line_ids')
            if records_with_lines and not self.env.context.get('portalgestor_skip_trabajo_fijo_edit_check'):
                raise ValidationError(_("Para cambiar mes o ano elimina primero los tramos de la plantilla."))
        return super().write(values)

    def _get_edit_snapshot_payload(self):
        self.ensure_one()
        return {
            'confirmado': bool(self.confirmado),
            'usuario_id': self.usuario_id.id or False,
            'month': self.month,
            'year': self.year,
            'lines': [
                {
                    'fecha': fields.Date.to_string(line.fecha),
                    'hora_inicio': line.hora_inicio,
                    'hora_fin': line.hora_fin,
                    'trabajador_id': line.trabajador_id.id,
                    'sequence': line.sequence,
                }
                for line in self.line_ids.sorted(key=lambda item: (item.fecha, item.hora_inicio, item.hora_fin, item.id))
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

    def _restore_edit_snapshot(self):
        Line = self.env['portalgestor.trabajo_fijo.linea']
        for record in self.filtered(lambda item: item.edit_session_pending and item.edit_snapshot_data):
            snapshot = json.loads(record.edit_snapshot_data)
            restore_context = dict(
                self.env.context,
                portalgestor_skip_trabajo_fijo_edit_check=True,
                portalgestor_skip_trabajo_fijo_line_check=True,
            )
            record.line_ids.with_context(**restore_context).unlink()
            record.with_context(**restore_context).write({
                'usuario_id': snapshot.get('usuario_id') or False,
                'month': snapshot.get('month'),
                'year': snapshot.get('year'),
                'confirmado': bool(snapshot.get('confirmado', True)),
                'edit_session_pending': False,
                'edit_snapshot_data': False,
            })
            if snapshot.get('lines'):
                Line.with_context(**restore_context).create([
                    {
                        'trabajo_fijo_id': record.id,
                        'fecha': fields.Date.to_date(line_data['fecha']),
                        'hora_inicio': line_data['hora_inicio'],
                        'hora_fin': line_data['hora_fin'],
                        'trabajador_id': line_data['trabajador_id'],
                        'sequence': line_data.get('sequence', 10),
                    }
                    for line_data in snapshot['lines']
                ])
        return True

    def action_editar(self):
        for record in self:
            record._ensure_current_user_can_manage_users(record.mapped('usuario_id'))
            if record.confirmado and not record.edit_session_pending:
                record._set_edit_snapshot()
        return True

    def action_descartar_edicion(self):
        for record in self:
            record._ensure_current_user_can_manage_users(record.mapped('usuario_id'))
        self._restore_edit_snapshot()
        return True

    def action_eliminar_borrador_no_verificado(self):
        for record in self:
            record._ensure_current_user_can_manage_users(record.mapped('usuario_id'))
            if not record.confirmado and not record.edit_session_pending and not record.line_ids:
                record.unlink()
        return True

    def action_eliminar_horario(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        self.unlink()
        return {'type': 'ir.actions.act_window_close'}

    @staticmethod
    def _build_feedback_action(message, notif_type='success', title=False, reload=False, close=False):
        params = {
            'message': message,
            'type': notif_type,
            'sticky': False,
        }
        if title:
            params['title'] = title
        if close:
            params['next'] = {'type': 'ir.actions.act_window_close'}
        elif reload:
            params['next'] = {'type': 'ir.actions.client', 'tag': 'reload'}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': params,
        }

    def action_open_seed_wizard(self):
        self.ensure_one()
        view = self.env.ref('portalGestor.portalgestor_trabajo_fijo_seed_wizard_form')
        return {
            'name': 'Sembrar semana',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.trabajo_fijo.seed.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': {'default_trabajo_fijo_id': self.id},
        }

    def action_open_copy_week_wizard(self):
        self.ensure_one()
        view = self.env.ref('portalGestor.portalgestor_trabajo_fijo_copy_week_wizard_form')
        return {
            'name': 'Copiar semana',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.trabajo_fijo.copy_week.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': {'default_trabajo_fijo_id': self.id},
        }

    def _replace_date_lines_from_source(self, source_lines, target_date):
        self.ensure_one()
        Line = self.env['portalgestor.trabajo_fijo.linea']
        self.line_ids.filtered(lambda line: line.fecha == target_date).unlink()
        return Line.create([
            {
                'trabajo_fijo_id': self.id,
                'fecha': target_date,
                'hora_inicio': source_line.hora_inicio,
                'hora_fin': source_line.hora_fin,
                'trabajador_id': source_line.trabajador_id.id,
                'sequence': source_line.sequence,
            }
            for source_line in source_lines.sorted(key=lambda item: (item.hora_inicio, item.hora_fin, item.id))
        ])

    def action_seed_week(self, source_date, weekday_indexes):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        source_date = fields.Date.to_date(source_date)
        if not source_date:
            raise ValidationError(_("Debes seleccionar un dia origen."))
        source_lines = self.line_ids.filtered(lambda line: line.fecha == source_date)
        if not source_lines:
            return self._build_feedback_action(
                _("El dia origen no tiene tramos para sembrar."),
                notif_type='warning',
                title=_("Nada que sembrar"),
            )
        week_start = source_date - timedelta(days=source_date.weekday())
        copied_days = 0
        copied_lines = 0
        for weekday_index in sorted(set(weekday_indexes)):
            target_date = week_start + timedelta(days=int(weekday_index))
            if target_date == source_date or target_date.month != int(self.month):
                continue
            self._replace_date_lines_from_source(source_lines, target_date)
            copied_days += 1
            copied_lines += len(source_lines)
        if not copied_days:
            return self._build_feedback_action(
                _("No se ha copiado ningun dia. Revisa que los dias destino pertenezcan al mes."),
                notif_type='warning',
                title=_("Sembrado no realizado"),
            )
        return self._build_feedback_action(
            _("Se sembraron %(days)s dias y %(lines)s tramos.") % {
                'days': copied_days,
                'lines': copied_lines,
            },
            title=_("Sembrado realizado"),
            close=True,
        )

    def _copy_week(self, source_week_number, scope='next'):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        try:
            source_week_number = int(source_week_number)
        except (TypeError, ValueError):
            source_week_number = 0
        weeks = self._get_week_dates(self.month, self.year)
        if source_week_number < 1 or source_week_number > len(weeks):
            return self._build_feedback_action(
                _("Selecciona una semana valida."),
                notif_type='warning',
                title=_("Copia no realizada"),
            )
        source_dates = [date_value for date_value in weeks[source_week_number - 1] if date_value.month == int(self.month)]
        copied_days = 0
        copied_lines = 0
        skipped_days = 0
        if scope == 'remaining':
            week_offsets = range(1, len(weeks) - source_week_number + 1)
        else:
            week_offsets = [1]
        for source_date in source_dates:
            source_lines = self.line_ids.filtered(lambda line: line.fecha == source_date)
            if not source_lines:
                continue
            for week_offset in week_offsets:
                target_date = source_date + timedelta(days=7 * week_offset)
                if target_date.month != int(self.month):
                    skipped_days += 1
                    continue
                self._replace_date_lines_from_source(source_lines, target_date)
                copied_days += 1
                copied_lines += len(source_lines)
        if not copied_days:
            return self._build_feedback_action(
                _("La semana seleccionada no tiene tramos copiables para el alcance elegido."),
                notif_type='warning',
                title=_("Nada que copiar"),
            )
        message = _("Se copiaron %(days)s dias y %(lines)s tramos.") % {
            'days': copied_days,
            'lines': copied_lines,
        }
        if skipped_days:
            message += "\n" + _("%(days)s dias no se copiaron porque salen del mes.") % {'days': skipped_days}
        if scope == 'remaining':
            title = _("Copia mensual realizada")
        else:
            title = _("Copia realizada")
        return self._build_feedback_action(message, title=title, close=True)

    def action_copy_week_to_next(self, source_week_number):
        return self._copy_week(source_week_number, scope='next')

    def action_copy_week_to_remaining(self, source_week_number):
        return self._copy_week(source_week_number, scope='remaining')

    def _get_target_specs(self):
        self.ensure_one()
        specs = defaultdict(list)
        for line in self.line_ids.sorted(key=lambda item: (item.fecha, item.hora_inicio, item.hora_fin, item.id)):
            if not line.fecha:
                continue
            specs[line.fecha].append({
                'line_id': line.id,
                'hora_inicio': line.hora_inicio,
                'hora_fin': line.hora_fin,
                'trabajador_id': line.trabajador_id.id,
                'trabajador': line.trabajador_id,
            })
        return specs

    def _run_target_checks(self, target_specs):
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
                for line in sorted(worker_lines, key=lambda item: (item['hora_inicio'], item['hora_fin'], item['line_id'])):
                    if previous_line and line['hora_inicio'] < previous_line['hora_fin']:
                        trabajador = line['trabajador'] or previous_line['trabajador']
                        raise ValidationError(
                            _("El AP %(worker)s tiene dos tramos solapados dentro del mismo horario.")
                            % {'worker': trabajador.display_name or trabajador.name}
                        )
                    previous_line = line
        return worker_dates

    def _collect_conflicts(self, target_specs):
        self.ensure_one()
        worker_dates = self._run_target_checks(target_specs)
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
            lambda line: line.trabajador_id and line.trabajo_fijo_id.id != self.id
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
                    elif not self.env.context.get('portalgestor_skip_trabajo_fijo_same_day_warning'):
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

    def _launch_batch_conflict_wizard(self, conflict_type, conflict_line_ids, summary_text):
        wizard = self.env['portalgestor.conflict.wizard'].create({
            'trabajo_fijo_id': self.id,
            'conflict_type': conflict_type,
            'batch_conflict_line_ids': [(6, 0, conflict_line_ids)],
            'info_resumen': summary_text,
        })
        return {
            'name': 'Conflicto de Horario',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.conflict.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _launch_info_wizard(self, summary_text):
        wizard = self.env['portalgestor.conflict.wizard'].create({
            'trabajo_fijo_id': self.id,
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

    def _apply_confirmation(self, target_specs):
        self.ensure_one()
        Assignment = self.env['portalgestor.asignacion']
        AssignmentLine = self.env['portalgestor.asignacion.linea']
        target_dates = sorted(target_specs)
        desired_line_ids = {
            line_data['line_id']
            for lines in target_specs.values()
            for line_data in lines
        }
        existing_generated_lines = AssignmentLine.search([
            ('trabajo_fijo_id', '=', self.id),
        ])
        existing_by_template_line = {
            line.trabajo_fijo_linea_id.id: line
            for line in existing_generated_lines
            if line.trabajo_fijo_linea_id
        }
        reusable_generated_by_date = defaultdict(lambda: self.env['portalgestor.asignacion.linea'])
        for line in existing_generated_lines.sorted(key=lambda item: (item.fecha, item.hora_inicio, item.hora_fin, item.id)):
            if line.trabajo_fijo_linea_id and line.trabajo_fijo_linea_id.id in desired_line_ids:
                continue
            reusable_generated_by_date[line.fecha] |= line
        consumed_generated_lines = self.env['portalgestor.asignacion.linea']
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
            for line_data in sorted(target_specs[target_date], key=lambda item: (item['hora_inicio'], item['hora_fin'], item['line_id'])):
                vals = {
                    'asignacion_id': assignment.id,
                    'hora_inicio': line_data['hora_inicio'],
                    'hora_fin': line_data['hora_fin'],
                    'trabajador_id': line_data['trabajador_id'],
                    'trabajo_fijo_id': self.id,
                    'trabajo_fijo_linea_id': line_data['line_id'],
                    'asignacion_mensual_id': False,
                    'asignacion_mensual_linea_id': False,
                }
                if 'asignacion_mensual_dia_id' in AssignmentLine._fields:
                    vals['asignacion_mensual_dia_id'] = False
                if 'asignacion_mensual_dia_linea_id' in AssignmentLine._fields:
                    vals['asignacion_mensual_dia_linea_id'] = False
                existing_line = existing_by_template_line.get(line_data['line_id'])
                if not existing_line and reusable_generated_by_date.get(target_date):
                    existing_line = reusable_generated_by_date[target_date][:1]
                    reusable_generated_by_date[target_date] = reusable_generated_by_date[target_date] - existing_line
                if existing_line:
                    consumed_generated_lines |= existing_line
                    if (
                        existing_line.asignacion_id != assignment
                        or existing_line.hora_inicio != line_data['hora_inicio']
                        or existing_line.hora_fin != line_data['hora_fin']
                        or existing_line.trabajador_id.id != line_data['trabajador_id']
                    ):
                        existing_line.with_context(
                            portalgestor_skip_fixed_sync=True,
                            portalgestor_skip_fixed_exception=True,
                        ).write(vals)
                    continue
                matching_manual_line = assignment.lineas_ids.filtered(
                    lambda line: not line.trabajo_fijo_id
                    and not line.asignacion_mensual_id
                    and line.hora_inicio == line_data['hora_inicio']
                    and line.hora_fin == line_data['hora_fin']
                    and line.trabajador_id.id == line_data['trabajador_id']
                )[:1]
                if matching_manual_line:
                    matching_manual_line.with_context(
                        portalgestor_skip_fixed_sync=True,
                        portalgestor_skip_fixed_exception=True,
                    ).write(vals)
                else:
                    AssignmentLine.with_context(
                        portalgestor_skip_fixed_sync=True,
                        portalgestor_skip_fixed_exception=True,
                    ).create(vals)

        consumed_generated_line_ids = set(consumed_generated_lines.ids)
        lines_to_remove = existing_generated_lines.filtered(
            lambda line: line.id not in consumed_generated_line_ids
            and line.trabajo_fijo_linea_id.id not in desired_line_ids
        )
        if lines_to_remove:
            lines_to_remove.with_context(
                portalgestor_skip_fixed_sync=True,
                portalgestor_skip_fixed_exception=True,
            ).unlink()
        touched_assignments = (
            existing_generated_lines.mapped('asignacion_id')
            | self.asignacion_linea_ids.mapped('asignacion_id')
            | Assignment.browse([assignment.id for assignment in assignments_by_date.values()])
        )
        touched_assignments.cleanup_empty_assignments()
        touched_assignments.exists().write({
            'confirmado': True,
            'gestor_owner_id': self.env.user.id,
            'edit_session_pending': False,
            'edit_snapshot_data': False,
        })
        self.with_context(portalgestor_skip_trabajo_fijo_edit_check=True).write({
            'confirmado': True,
            'edit_session_pending': False,
            'edit_snapshot_data': False,
            'gestor_owner_id': self.env.user.id,
        })
        return self._build_feedback_action(
            _("Trabajo fijo verificado y confirmado."),
            title=_("Horario actualizado"),
            reload=True,
        )

    def action_verificar_y_confirmar(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        target_specs = self._get_target_specs()
        if not target_specs:
            raise ValidationError(_("Debes anadir al menos un tramo en el trabajo fijo."))

        batch_conflicts = self._collect_conflicts(target_specs)
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
        if batch_conflicts['info_summary'] and not self.env.context.get('portalgestor_skip_trabajo_fijo_same_day_warning'):
            return self._launch_info_wizard(batch_conflicts['info_summary'])

        return self._apply_confirmation(target_specs)

    def unlink(self):
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        touched_assignments = self.mapped('asignacion_linea_ids.asignacion_id')
        self.mapped('asignacion_linea_ids').with_context(
            portalgestor_skip_fixed_sync=True,
            portalgestor_skip_fixed_exception=True,
        ).unlink()
        touched_assignments.cleanup_empty_assignments()
        return super().unlink()

    @api.model
    def _migrate_from_monthly_template(self):
        Legacy = self.env['portalgestor.asignacion.mensual'].sudo()
        Line = self.env['portalgestor.trabajo_fijo.linea'].sudo()
        legacy_records = Legacy.search([('schedule_type', '=', 'monthly_template')])
        migration_context = dict(
            self.env.context,
            portalgestor_skip_trabajo_fijo_edit_check=True,
            portalgestor_skip_trabajo_fijo_line_check=True,
        )
        for legacy in legacy_records:
            fixed = self.sudo().search([('legacy_asignacion_mensual_id', '=', legacy.id)], limit=1)
            vals = {
                'usuario_id': legacy.usuario_id.id,
                'month': legacy.month,
                'year': legacy.year,
                'confirmado': legacy.confirmado,
                'gestor_owner_id': legacy.gestor_owner_id.id or legacy.write_uid.id or legacy.create_uid.id,
                'edit_session_pending': False,
                'edit_snapshot_data': False,
                'legacy_asignacion_mensual_id': legacy.id,
            }
            if fixed:
                fixed.with_context(**migration_context).write(vals)
            else:
                fixed = self.sudo().with_context(**migration_context).create(vals)

            new_lines_by_legacy_line = {
                line.legacy_template_day_line_id.id: line
                for line in fixed.line_ids
                if line.legacy_template_day_line_id
            }
            legacy_line_ids = set()
            for legacy_line in legacy.template_day_line_ids:
                target_date = legacy_line.fecha or legacy_line.template_day_id.fecha
                if not target_date or not legacy_line.trabajador_id:
                    continue
                legacy_line_ids.add(legacy_line.id)
                line_vals = {
                    'trabajo_fijo_id': fixed.id,
                    'fecha': target_date,
                    'hora_inicio': legacy_line.hora_inicio,
                    'hora_fin': legacy_line.hora_fin,
                    'trabajador_id': legacy_line.trabajador_id.id,
                    'legacy_template_day_line_id': legacy_line.id,
                }
                new_line = new_lines_by_legacy_line.get(legacy_line.id)
                if new_line:
                    new_line.with_context(**migration_context).write(line_vals)
                else:
                    new_line = Line.with_context(**migration_context).create(line_vals)
                    new_lines_by_legacy_line[legacy_line.id] = new_line

            stale_lines = fixed.line_ids.filtered(
                lambda line: line.legacy_template_day_line_id and line.legacy_template_day_line_id.id not in legacy_line_ids
            )
            if stale_lines:
                stale_lines.with_context(**migration_context).unlink()

            for generated_line in legacy.asignacion_linea_ids:
                new_template_line = new_lines_by_legacy_line.get(generated_line.asignacion_mensual_dia_linea_id.id)
                if not new_template_line:
                    continue
                generated_line.sudo().with_context(
                    portalgestor_skip_fixed_sync=True,
                    portalgestor_skip_fixed_exception=True,
                ).write({
                    'trabajo_fijo_id': fixed.id,
                    'trabajo_fijo_linea_id': new_template_line.id,
                })
        return True


class TrabajoFijoLinea(models.Model):
    _name = 'portalgestor.trabajo_fijo.linea'
    _description = 'Tramo de Trabajo Fijo Mensual'
    _order = 'fecha, hora_inicio, hora_fin, sequence, id'

    trabajo_fijo_id = fields.Many2one(
        'portalgestor.trabajo_fijo',
        string='Trabajo fijo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    fecha = fields.Date(string='Fecha', required=True, index=True)
    week_number = fields.Integer(string='Semana', compute='_compute_date_parts', store=True, index=True)
    weekday_index = fields.Integer(string='Dia semana', compute='_compute_date_parts', store=True)
    weekday_label = fields.Char(string='Dia', compute='_compute_date_parts', store=True)
    usuario_zona_trabajo_id = fields.Many2one(
        related='trabajo_fijo_id.usuario_zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    usuario_localidad_id = fields.Many2one(
        related='trabajo_fijo_id.usuario_localidad_id',
        string='Localidad del Usuario',
        readonly=True,
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
    legacy_template_day_line_id = fields.Many2one(
        'portalgestor.asignacion.mensual.dia.linea',
        string='Tramo legacy',
        ondelete='set null',
        copy=False,
        index=True,
    )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_trabajo_fijo_linea_fecha_idx',
            tablename=self._table,
            expressions=['trabajo_fijo_id', 'fecha'],
        )

    @api.depends('fecha', 'trabajo_fijo_id.month', 'trabajo_fijo_id.year')
    def _compute_date_parts(self):
        for record in self:
            if not record.fecha:
                record.week_number = 0
                record.weekday_index = 0
                record.weekday_label = ''
                continue
            date_value = fields.Date.to_date(record.fecha)
            record.weekday_index = date_value.weekday()
            record.weekday_label = WEEKDAY_LABELS.get(record.weekday_index, '')
            record.week_number = record._get_week_number_in_parent_month(date_value)

    def _get_week_number_in_parent_month(self, date_value):
        self.ensure_one()
        if not self.trabajo_fijo_id.month or not self.trabajo_fijo_id.year:
            return 0
        for week_number, week_dates in enumerate(
            TrabajoFijo._get_week_dates(self.trabajo_fijo_id.month, self.trabajo_fijo_id.year),
            start=1,
        ):
            if date_value in week_dates:
                return week_number
        return 0

    def _ensure_parent_editable(self, parent_records):
        if self.env.context.get('portalgestor_skip_trabajo_fijo_line_check'):
            return
        parent_records.invalidate_recordset(['confirmado', 'edit_session_pending'])
        parent_records._ensure_current_user_can_manage_users(parent_records.mapped('usuario_id'))
        locked_records = parent_records.filtered(lambda record: record.confirmado and not record.edit_session_pending)
        if locked_records:
            raise ValidationError(_("Pulsa Modificar Horario antes de cambiar un trabajo fijo confirmado."))

    @api.model_create_multi
    def create(self, vals_list):
        parent_ids = [vals.get('trabajo_fijo_id') for vals in vals_list if vals.get('trabajo_fijo_id')]
        parent_records = self.env['portalgestor.trabajo_fijo'].browse(parent_ids).exists()
        if parent_records:
            self._ensure_parent_editable(parent_records)
        records = super().create(vals_list)
        records._check_dates_inside_parent_month()
        return records

    def write(self, vals):
        parent_records = self.mapped('trabajo_fijo_id')
        if vals.get('trabajo_fijo_id'):
            parent_records |= self.env['portalgestor.trabajo_fijo'].browse(vals['trabajo_fijo_id']).exists()
        self._ensure_parent_editable(parent_records)
        result = super().write(vals)
        self._check_dates_inside_parent_month()
        return result

    def unlink(self):
        parent_records = self.mapped('trabajo_fijo_id')
        self._ensure_parent_editable(parent_records)
        return super().unlink()

    @api.constrains('fecha', 'trabajo_fijo_id')
    def _check_dates_inside_parent_month(self):
        for record in self:
            if not record.fecha or not record.trabajo_fijo_id:
                continue
            if record.fecha < record.trabajo_fijo_id.fecha_inicio or record.fecha > record.trabajo_fijo_id.fecha_fin:
                raise ValidationError(_("La fecha del tramo debe pertenecer al mes del trabajo fijo."))

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

    trabajo_fijo_id = fields.Many2one(
        'portalgestor.trabajo_fijo',
        string='Trabajo fijo V2',
        ondelete='set null',
        index=True,
    )
    trabajo_fijo_linea_id = fields.Many2one(
        'portalgestor.trabajo_fijo.linea',
        string='Tramo de trabajo fijo V2',
        ondelete='set null',
        index=True,
    )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_trabajo_fijo_fecha_idx',
            tablename=self._table,
            expressions=['trabajo_fijo_id', 'fecha'],
        )
        create_index(
            self.env.cr,
            indexname='portalgestor_linea_trabajo_fijo_linea_fecha_idx',
            tablename=self._table,
            expressions=['trabajo_fijo_linea_id', 'fecha'],
        )

    def _detach_fixed_days_when_worker_changed(self, assignments, monthly_ids_by_assignment):
        detached_lines = super()._detach_fixed_days_when_worker_changed(assignments, monthly_ids_by_assignment)
        if (
            self.env.context.get('portalgestor_skip_fixed_sync')
            or self.env.context.get('portalgestor_skip_fixed_exception')
        ):
            return detached_lines

        lines_to_detach = self.browse()
        fixed_to_unconfirm = self.env['portalgestor.trabajo_fijo']
        for assignment in assignments.exists():
            for fixed in assignment.lineas_ids.mapped('trabajo_fijo_id').exists():
                template_lines = fixed.line_ids.filtered(lambda line: line.fecha == assignment.fecha)
                generated_lines = assignment.lineas_ids.filtered(lambda line: line.trabajo_fijo_id == fixed)
                generated_by_template = {
                    line.trabajo_fijo_linea_id.id: line
                    for line in generated_lines
                    if line.trabajo_fijo_linea_id
                }
                mismatch = len(generated_lines) != len(template_lines)
                for template_line in template_lines:
                    generated_line = generated_by_template.get(template_line.id)
                    if not generated_line:
                        mismatch = True
                        break
                    if (
                        generated_line.hora_inicio != template_line.hora_inicio
                        or generated_line.hora_fin != template_line.hora_fin
                        or generated_line.trabajador_id != template_line.trabajador_id
                    ):
                        mismatch = True
                        break
                if mismatch:
                    lines_to_detach |= generated_lines
                    fixed_to_unconfirm |= fixed

        if lines_to_detach:
            lines_to_detach.with_context(
                portalgestor_skip_calendar_notify=True,
                portalgestor_skip_fixed_exception=True,
            ).write({
                'trabajo_fijo_id': False,
                'trabajo_fijo_linea_id': False,
            })
        if fixed_to_unconfirm:
            fixed_to_unconfirm.with_context(portalgestor_skip_trabajo_fijo_edit_check=True).write({
                'confirmado': False,
            })
        return detached_lines | lines_to_detach


class TrabajoFijoSeedWizard(models.TransientModel):
    _name = 'portalgestor.trabajo_fijo.seed.wizard'
    _description = 'Sembrar semana de trabajo fijo'

    trabajo_fijo_id = fields.Many2one(
        'portalgestor.trabajo_fijo',
        string='Trabajo fijo',
        required=True,
        ondelete='cascade',
    )
    source_date = fields.Date(string='Dia origen', required=True)
    monday = fields.Boolean(string='Lun')
    tuesday = fields.Boolean(string='Mar')
    wednesday = fields.Boolean(string='Mie')
    thursday = fields.Boolean(string='Jue')
    friday = fields.Boolean(string='Vie')
    saturday = fields.Boolean(string='Sab')
    sunday = fields.Boolean(string='Dom')

    def action_apply(self):
        self.ensure_one()
        weekday_indexes = []
        if self.monday:
            weekday_indexes.append(0)
        if self.tuesday:
            weekday_indexes.append(1)
        if self.wednesday:
            weekday_indexes.append(2)
        if self.thursday:
            weekday_indexes.append(3)
        if self.friday:
            weekday_indexes.append(4)
        if self.saturday:
            weekday_indexes.append(5)
        if self.sunday:
            weekday_indexes.append(6)
        if not weekday_indexes:
            raise ValidationError(_("Selecciona al menos un dia destino."))
        return self.trabajo_fijo_id.action_seed_week(self.source_date, weekday_indexes)


class TrabajoFijoCopyWeekWizard(models.TransientModel):
    _name = 'portalgestor.trabajo_fijo.copy_week.wizard'
    _description = 'Copiar semana de trabajo fijo'

    trabajo_fijo_id = fields.Many2one(
        'portalgestor.trabajo_fijo',
        string='Trabajo fijo',
        required=True,
        ondelete='cascade',
    )
    source_week_number = fields.Integer(string='Semana origen', required=True, default=1)

    def action_apply(self):
        self.ensure_one()
        return self.trabajo_fijo_id.action_copy_week_to_next(self.source_week_number)

    def action_apply_next(self):
        self.ensure_one()
        return self.trabajo_fijo_id.action_copy_week_to_next(self.source_week_number)

    def action_apply_remaining(self):
        self.ensure_one()
        return self.trabajo_fijo_id.action_copy_week_to_remaining(self.source_week_number)
