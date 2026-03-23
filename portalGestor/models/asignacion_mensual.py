# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AsignacionMensual(models.Model):
    _name = 'portalgestor.asignacion.mensual'
    _description = 'Trabajo Fijo'
    _order = 'fecha_inicio desc, usuario_id, id desc'

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
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        related='usuario_id.zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    fecha_inicio = fields.Date(
        string='Dia inicio',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    fecha_fin = fields.Date(
        string='Dia fin',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    linea_fija_ids = fields.One2many(
        'portalgestor.asignacion.mensual.linea',
        'asignacion_mensual_id',
        string='Tramos fijos',
        copy=True,
    )
    asignacion_linea_ids = fields.One2many(
        'portalgestor.asignacion.linea',
        'asignacion_mensual_id',
        string='Asignaciones generadas',
    )
    confirmado = fields.Boolean(string='Horario Confirmado', default=False)
    excepcion_ids = fields.One2many(
        'portalgestor.asignacion.mensual.excepcion',
        'asignacion_mensual_id',
        string='Excepciones por dia',
    )
    total_dias_generados = fields.Integer(
        string='Dias generados',
        compute='_compute_generation_totals',
    )
    total_lineas_generadas = fields.Integer(
        string='Lineas generadas',
        compute='_compute_generation_totals',
    )

    @api.depends('usuario_id.name', 'fecha_inicio', 'fecha_fin', 'linea_fija_ids')
    def _compute_name(self):
        for record in self:
            if not record.usuario_id or not record.fecha_inicio or not record.fecha_fin:
                record.name = _('Nuevo Trabajo Fijo')
                continue

            record.name = _(
                '%(usuario)s | %(fecha_inicio)s -> %(fecha_fin)s (%(tramos)s tramos)'
            ) % {
                'usuario': record.usuario_id.name,
                'fecha_inicio': fields.Date.to_string(record.fecha_inicio),
                'fecha_fin': fields.Date.to_string(record.fecha_fin),
                'tramos': len(record.linea_fija_ids),
            }

    @api.constrains('usuario_id')
    def _check_usuario_has_ap_service(self):
        for record in self:
            if record.usuario_id and not record.usuario_id.has_ap_service:
                raise ValidationError(_("Solo puedes asignar trabajos fijos a usuarios con el servicio AP activo."))

    @api.depends('asignacion_linea_ids', 'asignacion_linea_ids.fecha')
    def _compute_generation_totals(self):
        for record in self:
            fechas = {fecha for fecha in record.asignacion_linea_ids.mapped('fecha') if fecha}
            record.total_dias_generados = len(fechas)
            record.total_lineas_generadas = len(record.asignacion_linea_ids)

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_date_range(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin and record.fecha_inicio > record.fecha_fin:
                raise ValidationError(_("El dia inicio debe ser menor o igual al dia fin."))

    @api.constrains('linea_fija_ids')
    def _check_lineas_fijas(self):
        for record in self:
            if not record.linea_fija_ids:
                raise ValidationError(_("Debes anadir al menos un tramo fijo."))

    def _get_target_dates(self):
        self.ensure_one()
        if not self.fecha_inicio or not self.fecha_fin:
            return []

        target_dates = []
        current_date = fields.Date.to_date(self.fecha_inicio)
        end_date = fields.Date.to_date(self.fecha_fin)
        while current_date <= end_date:
            target_dates.append(current_date)
            current_date += timedelta(days=1)
        return target_dates

    def _mark_unconfirmed(self):
        if not self:
            return
        self.env.cr.execute(
            """
                UPDATE portalgestor_asignacion_mensual
                   SET confirmado = FALSE
                 WHERE id IN %s
                   AND confirmado = TRUE
            """,
            [tuple(self.ids)],
        )
        self.invalidate_recordset(['confirmado'])

    def _get_manual_exception_dates(self, target_dates):
        self.ensure_one()
        if not target_dates:
            return set()

        exceptions = self.env['portalgestor.asignacion.mensual.excepcion'].search([
            ('asignacion_mensual_id', '=', self.id),
            ('fecha', 'in', target_dates),
        ])
        return {
            fields.Date.to_string(exception.fecha)
            for exception in exceptions
            if exception.fecha
        }

    def _sync_generated_assignments(self):
        Assignment = self.env['portalgestor.asignacion']
        AssignmentLine = self.env['portalgestor.asignacion.linea']

        for record in self:
            target_dates = record._get_target_dates()
            target_dates_by_key = {
                fields.Date.to_string(target_date): target_date
                for target_date in target_dates
            }
            fixed_lines = record.linea_fija_ids.sorted(
                key=lambda line: (line.hora_inicio, line.hora_fin, line.id)
            )
            today = fields.Date.to_date(fields.Date.context_today(record))
            manual_exception_dates = record._get_manual_exception_dates(target_dates)
            target_keys = set()
            active_dates = set()
            for date_key, target_date in target_dates_by_key.items():
                if record.usuario_id.baja and target_date >= today:
                    continue
                if date_key in manual_exception_dates:
                    continue

                for fixed_line in fixed_lines:
                    if fixed_line.trabajador_id.baja and target_date >= today:
                        continue
                    target_keys.add((date_key, fixed_line.id))
                    active_dates.add(date_key)

            existing_lines_by_key = {}
            lines_to_remove = AssignmentLine.browse()
            touched_assignments = record.asignacion_linea_ids.mapped('asignacion_id')

            for line in record.asignacion_linea_ids.sorted(
                key=lambda line: (line.fecha, line.hora_inicio, line.hora_fin, line.id)
            ):
                line_key = (
                    fields.Date.to_string(line.fecha),
                    line.asignacion_mensual_linea_id.id,
                )
                if not line_key[1] or line_key not in target_keys or line_key in existing_lines_by_key:
                    lines_to_remove |= line
                    continue
                existing_lines_by_key[line_key] = line

            if lines_to_remove:
                touched_assignments |= lines_to_remove.mapped('asignacion_id')
                lines_to_remove.with_context(
                    portalgestor_skip_fixed_sync=True,
                    portalgestor_skip_fixed_exception=True,
                ).unlink()

            assignments_by_date = {}
            if active_dates:
                assignments_by_date = {
                    fields.Date.to_string(assignment.fecha): assignment
                    for assignment in Assignment.search(
                        [
                            ('usuario_id', '=', record.usuario_id.id),
                            ('fecha', 'in', [
                                target_dates_by_key[date_key]
                                for date_key in sorted(active_dates)
                            ]),
                        ]
                    )
                }

            for date_key, target_date in target_dates_by_key.items():
                if date_key not in active_dates:
                    continue
                assignment = assignments_by_date.get(date_key)
                if not assignment:
                    assignment = Assignment.create({
                        'usuario_id': record.usuario_id.id,
                        'fecha': target_date,
                    })
                    assignments_by_date[date_key] = assignment

                touched_assignments |= assignment
                for fixed_line in fixed_lines:
                    line_key = (date_key, fixed_line.id)
                    if line_key not in target_keys:
                        continue
                    line_vals = fixed_line._get_generated_line_vals(assignment)
                    existing_line = existing_lines_by_key.get(line_key)
                    if existing_line:
                        touched_assignments |= existing_line.asignacion_id
                        if (
                            existing_line.asignacion_id != assignment
                            or existing_line.hora_inicio != fixed_line.hora_inicio
                            or existing_line.hora_fin != fixed_line.hora_fin
                            or existing_line.trabajador_id != fixed_line.trabajador_id
                            or existing_line.asignacion_mensual_id != record
                            or existing_line.asignacion_mensual_linea_id != fixed_line
                        ):
                            existing_line.with_context(
                                portalgestor_skip_fixed_sync=True,
                                portalgestor_skip_fixed_exception=True,
                            ).write(line_vals)
                            touched_assignments |= existing_line.asignacion_id
                    else:
                        generated_line = AssignmentLine.with_context(
                            portalgestor_skip_fixed_sync=True,
                            portalgestor_skip_fixed_exception=True,
                        ).create(line_vals)
                        touched_assignments |= generated_line.asignacion_id

            if touched_assignments:
                touched_assignments.cleanup_empty_assignments()
                touched_assignments.exists().write({'confirmado': False})
                record._mark_unconfirmed()

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals, confirmado=vals.get('confirmado', False)) for vals in vals_list]
        records = super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).create(vals_list)
        records._sync_generated_assignments()
        return records

    def write(self, vals):
        if set(vals) == {'confirmado'}:
            return super(
                AsignacionMensual,
                self.with_context(portalgestor_skip_fixed_sync=True),
            ).write(vals)
        if 'confirmado' not in vals:
            vals = dict(vals, confirmado=False)
        result = super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).write(vals)
        self._sync_generated_assignments()
        return result

    def action_verificar_y_confirmar(self):
        self.ensure_one()
        if not self.env.context.get('portalgestor_skip_fixed_sync_before_verify'):
            self._sync_generated_assignments()
        asignaciones_pendientes = self.asignacion_linea_ids.mapped('asignacion_id').exists().sorted(
            key=lambda asignacion: (asignacion.fecha, asignacion.id)
        ).filtered(lambda asignacion: not asignacion.confirmado)

        for asignacion in asignaciones_pendientes:
            result = asignacion._get_verification_action(asignacion_mensual_id=self.id)
            if isinstance(result, dict):
                return result
            asignacion.confirmado = True

        self.confirmado = True
        return True

    def action_editar(self):
        self.ensure_one()
        self.confirmado = False
        self.asignacion_linea_ids.mapped('asignacion_id').write({'confirmado': False})
        return True

    def unlink(self):
        touched_assignments = self.mapped('asignacion_linea_ids.asignacion_id')
        generated_lines = self.mapped('asignacion_linea_ids')
        exception_keys = {
            (exception.asignacion_mensual_id.id, exception.fecha)
            for exception in self.mapped('excepcion_ids')
            if exception.asignacion_mensual_id and exception.fecha
        }
        generated_lines = generated_lines.filtered(
            lambda line: (line.asignacion_mensual_id.id, line.fecha) not in exception_keys
        )
        generated_lines.with_context(
            portalgestor_skip_fixed_sync=True,
            portalgestor_skip_fixed_exception=True,
        ).unlink()
        touched_assignments.cleanup_empty_assignments()
        return super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).unlink()


class AsignacionMensualLinea(models.Model):
    _name = 'portalgestor.asignacion.mensual.linea'
    _description = 'Tramo de Trabajo Fijo'
    _order = 'hora_inicio, hora_fin, id'

    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Trabajo fijo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        related='asignacion_mensual_id.usuario_zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    hora_inicio = fields.Float(string='Hora Inicio', required=True)
    hora_fin = fields.Float(string='Hora Fin', required=True)
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='Trabajador',
        required=True,
        ondelete='restrict',
        index=True,
    )
    asignacion_linea_ids = fields.One2many(
        'portalgestor.asignacion.linea',
        'asignacion_mensual_linea_id',
        string='Asignaciones generadas',
    )

    def _get_generated_line_vals(self, assignment):
        self.ensure_one()
        return {
            'asignacion_id': assignment.id,
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
            'trabajador_id': self.trabajador_id.id,
            'asignacion_mensual_id': self.asignacion_mensual_id.id,
            'asignacion_mensual_linea_id': self.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('portalgestor_skip_fixed_sync'):
            records.mapped('asignacion_mensual_id')._sync_generated_assignments()
        return records

    def write(self, vals):
        parent_records = self.mapped('asignacion_mensual_id')
        result = super().write(vals)
        if not self.env.context.get('portalgestor_skip_fixed_sync'):
            (parent_records | self.mapped('asignacion_mensual_id')).exists()._sync_generated_assignments()
        return result

    def unlink(self):
        parent_records = self.mapped('asignacion_mensual_id')
        result = super().unlink()
        if not self.env.context.get('portalgestor_skip_fixed_sync'):
            parent_records.exists()._sync_generated_assignments()
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
