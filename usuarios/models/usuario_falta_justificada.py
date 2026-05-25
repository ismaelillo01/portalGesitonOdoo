# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UsuarioFaltaJustificada(models.Model):
    _name = 'usuarios.falta.justificada'
    _description = 'Falta justificada de usuario'
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
        string='Grupo',
        store=True,
        readonly=True,
        index=True,
    )
    fecha_inicio = fields.Date(string='Fecha inicio', required=True, index=True)
    fecha_fin = fields.Date(string='Fecha fin', required=True, index=True)
    motivo = fields.Text(string='Motivo')

    @api.depends('usuario_id.display_name', 'fecha_inicio', 'fecha_fin')
    def _compute_name(self):
        for record in self:
            if not record.usuario_id or not record.fecha_inicio:
                record.name = _('Nueva falta justificada')
                continue
            start_label = fields.Date.to_string(record.fecha_inicio)
            end_label = fields.Date.to_string(record.fecha_fin)
            date_label = start_label if record.fecha_inicio == record.fecha_fin else '%s -> %s' % (
                start_label,
                end_label,
            )
            record.name = _('%(usuario)s %(date)s') % {
                'usuario': record.usuario_id.display_name or record.usuario_id.name,
                'date': date_label,
            }

    def _ensure_current_user_can_manage_users(self, usuarios):
        usuarios._ensure_current_user_can_manage_target_groups(usuarios.mapped('grupo'))

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_dates(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin and record.fecha_inicio > record.fecha_fin:
                raise ValidationError(_("La fecha de inicio no puede ser posterior a la fecha de fin."))

    @api.constrains('usuario_id', 'fecha_inicio', 'fecha_fin')
    def _check_overlapping_user_absences(self):
        for record in self:
            if not record.usuario_id or not record.fecha_inicio or not record.fecha_fin:
                continue
            overlapping_absence = self.search([
                ('id', '!=', record.id),
                ('usuario_id', '=', record.usuario_id.id),
                ('fecha_inicio', '<=', record.fecha_fin),
                ('fecha_fin', '>=', record.fecha_inicio),
            ], limit=1)
            if overlapping_absence:
                raise ValidationError(
                    _("El usuario %(usuario)s ya tiene una falta justificada en un rango solapado.")
                    % {'usuario': record.usuario_id.display_name or record.usuario_id.name}
                )

    @api.model
    def _get_absent_dates_by_user(self, usuario_ids, date_start, date_end):
        usuario_ids = usuario_ids.ids if hasattr(usuario_ids, 'ids') else usuario_ids
        usuario_ids = [usuario_id for usuario_id in (usuario_ids or []) if usuario_id]
        start_date = fields.Date.to_date(date_start) if date_start else False
        end_date = fields.Date.to_date(date_end) if date_end else False
        if not usuario_ids or not start_date or not end_date or end_date < start_date:
            return {}

        absences = self.search([
            ('usuario_id', 'in', usuario_ids),
            ('fecha_inicio', '<=', end_date),
            ('fecha_fin', '>=', start_date),
        ])
        dates_by_user = defaultdict(set)
        for absence in absences:
            current_date = max(absence.fecha_inicio, start_date)
            stop_date = min(absence.fecha_fin, end_date)
            while current_date <= stop_date:
                dates_by_user[absence.usuario_id.id].add(current_date)
                current_date += timedelta(days=1)
        return dict(dates_by_user)

    @api.model_create_multi
    def create(self, vals_list):
        usuario_ids = [vals.get('usuario_id') for vals in vals_list if vals.get('usuario_id')]
        if usuario_ids:
            self._ensure_current_user_can_manage_users(self.env['usuarios.usuario'].browse(usuario_ids).exists())
        return super().create(vals_list)

    def write(self, vals):
        target_users = self.mapped('usuario_id')
        if vals.get('usuario_id'):
            target_users |= self.env['usuarios.usuario'].browse(vals['usuario_id']).exists()
        self._ensure_current_user_can_manage_users(target_users)
        return super().write(vals)

    def unlink(self):
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        return super().unlink()


class Usuario(models.Model):
    _inherit = 'usuarios.usuario'

    falta_justificada_ids = fields.One2many(
        'usuarios.falta.justificada',
        'usuario_id',
        string='Faltas justificadas',
    )
