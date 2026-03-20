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
            target_keys = {
                (date_key, fixed_line.id)
                for date_key in target_dates_by_key
                for fixed_line in fixed_lines
            }
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
                lines_to_remove.unlink()

            assignments_by_date = {}
            if target_dates:
                assignments_by_date = {
                    fields.Date.to_string(assignment.fecha): assignment
                    for assignment in Assignment.search(
                        [
                            ('usuario_id', '=', record.usuario_id.id),
                            ('fecha', 'in', target_dates),
                        ]
                    )
                }

            for date_key, target_date in target_dates_by_key.items():
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
                            existing_line.write(line_vals)
                            touched_assignments |= existing_line.asignacion_id
                    else:
                        generated_line = AssignmentLine.create(line_vals)
                        touched_assignments |= generated_line.asignacion_id

            if touched_assignments:
                touched_assignments.cleanup_empty_assignments()
                touched_assignments.exists().write({'confirmado': False})

    @api.model_create_multi
    def create(self, vals_list):
        records = super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).create(vals_list)
        records._sync_generated_assignments()
        return records

    def write(self, vals):
        result = super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).write(vals)
        self._sync_generated_assignments()
        return result

    def unlink(self):
        touched_assignments = self.mapped('asignacion_linea_ids.asignacion_id')
        generated_lines = self.mapped('asignacion_linea_ids')
        generated_lines.unlink()
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
