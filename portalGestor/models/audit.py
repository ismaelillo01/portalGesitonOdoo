# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


ACTION_SELECTION = [
    ('create', 'Creado'),
    ('add_line', 'Anadido tramo'),
    ('write', 'Modificado'),
    ('confirm', 'Confirmado'),
    ('edit', 'Editado'),
    ('discard', 'Descartado'),
    ('delete', 'Eliminado'),
    ('release', 'Liberado'),
]

TARGET_SELECTION = [
    ('daily_assignment', 'Horario diario'),
    ('daily_line', 'Tramo diario'),
    ('legacy_fixed', 'Trabajo fijo legacy'),
    ('legacy_fixed_line', 'Tramo trabajo fijo legacy'),
    ('fixed_work', 'Trabajo fijo'),
    ('fixed_work_line', 'Tramo trabajo fijo'),
]

MONTH_LABELS = {
    '1': 'enero',
    '2': 'febrero',
    '3': 'marzo',
    '4': 'abril',
    '5': 'mayo',
    '6': 'junio',
    '7': 'julio',
    '8': 'agosto',
    '9': 'septiembre',
    '10': 'octubre',
    '11': 'noviembre',
    '12': 'diciembre',
}


class PortalGestorAuditLog(models.Model):
    _name = 'portalgestor.audit.log'
    _description = 'Auditoria de acciones de PortalGestor'
    _order = 'event_datetime desc, id desc'
    _rec_name = 'summary'

    event_datetime = fields.Datetime(
        string='Fecha y hora',
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        index=True,
    )
    event_date = fields.Date(
        string='Fecha',
        compute='_compute_event_date',
        store=True,
        readonly=True,
        index=True,
    )
    gestor_id = fields.Many2one(
        'res.users',
        string='Gestor',
        required=True,
        readonly=True,
        ondelete='restrict',
        default=lambda self: self.env.user,
        index=True,
    )
    action_type = fields.Selection(
        ACTION_SELECTION,
        string='Accion',
        required=True,
        readonly=True,
        index=True,
    )
    target_type = fields.Selection(
        TARGET_SELECTION,
        string='Tipo',
        required=True,
        readonly=True,
        index=True,
    )
    summary = fields.Char(string='Resumen', required=True, readonly=True, index=True)
    detail = fields.Text(string='Detalle', readonly=True)

    usuario_id = fields.Many2one('usuarios.usuario', string='Usuario', readonly=True, ondelete='set null')
    trabajador_id = fields.Many2one('trabajadores.trabajador', string='AP', readonly=True, ondelete='set null')
    asignacion_id = fields.Many2one('portalgestor.asignacion', string='Horario diario', readonly=True, ondelete='set null')
    trabajo_fijo_id = fields.Many2one('portalgestor.trabajo_fijo', string='Trabajo fijo', readonly=True, ondelete='set null')
    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Trabajo fijo legacy',
        readonly=True,
        ondelete='set null',
    )

    usuario_name = fields.Char(string='Usuario legible', readonly=True, index=True)
    trabajador_name = fields.Char(string='AP legible', readonly=True, index=True)
    usuario_grupo = fields.Selection(
        [('intecum', 'Intecum'), ('agusto', 'Agusto')],
        string='Grupo del usuario',
        readonly=True,
        index=True,
    )
    target_label = fields.Char(string='Objeto', readonly=True, index=True)
    date_label = fields.Char(string='Fecha legible', readonly=True, index=True)
    month_label = fields.Char(string='Mes legible', readonly=True, index=True)
    technical_payload = fields.Text(string='Datos tecnicos', readonly=True)

    @api.depends('event_datetime')
    def _compute_event_date(self):
        for record in self:
            record.event_date = fields.Date.to_date(record.event_datetime) if record.event_datetime else False

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('portalgestor_allow_audit_create'):
            raise AccessError(_("Los registros de auditoria solo se crean desde PortalGestor."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('portalgestor_allow_audit_maintenance'):
            raise AccessError(_("Los registros de auditoria no se pueden modificar."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('portalgestor_allow_audit_maintenance'):
            raise AccessError(_("Los registros de auditoria no se pueden eliminar."))
        return super().unlink()

    @api.model
    def should_skip_schedule_audit(self):
        skip_keys = (
            'portalgestor_skip_audit',
            'portalgestor_skip_fixed_sync',
            'portalgestor_skip_fixed_exception',
            'portalgestor_skip_trabajo_fijo_line_check',
        )
        return any(self.env.context.get(key) for key in skip_keys)

    @api.model
    def display_record_name(self, record):
        if not record:
            return ''
        record = record.exists()
        if not record:
            return ''
        return record.display_name or getattr(record, 'name', '') or ''

    @api.model
    def format_date_label(self, value):
        date_value = fields.Date.to_date(value)
        return date_value.strftime('%d/%m/%Y') if date_value else ''

    @api.model
    def format_hour_label(self, value):
        total_minutes = int(round((value or 0.0) * 60))
        total_minutes = max(total_minutes, 0)
        return '%02d:%02d' % (total_minutes // 60, total_minutes % 60)

    @api.model
    def format_hour_range_label(self, hour_start, hour_end):
        return '%s-%s' % (self.format_hour_label(hour_start), self.format_hour_label(hour_end))

    @api.model
    def format_month_label(self, month, year):
        month_key = str(month) if month else ''
        month_label = MONTH_LABELS.get(month_key, month_key)
        return '%s %s' % (month_label, year or '')

    @api.model
    def create_event(
        self,
        action_type,
        target_type,
        summary,
        detail=False,
        usuario=False,
        trabajador=False,
        asignacion=False,
        trabajo_fijo=False,
        asignacion_mensual=False,
        usuario_name=False,
        trabajador_name=False,
        usuario_grupo=False,
        target_label=False,
        date_label=False,
        month_label=False,
        technical_payload=False,
    ):
        usuario = usuario.exists()[:1] if usuario else self.env['usuarios.usuario']
        trabajador = trabajador.exists()[:1] if trabajador else self.env['trabajadores.trabajador']
        asignacion = asignacion.exists()[:1] if asignacion else self.env['portalgestor.asignacion']
        trabajo_fijo = trabajo_fijo.exists()[:1] if trabajo_fijo else self.env['portalgestor.trabajo_fijo']
        asignacion_mensual = (
            asignacion_mensual.exists()[:1]
            if asignacion_mensual
            else self.env['portalgestor.asignacion.mensual']
        )

        payload_text = False
        if technical_payload:
            try:
                payload_text = json.dumps(technical_payload, ensure_ascii=False, default=str, sort_keys=True)
            except TypeError:
                payload_text = json.dumps({'payload': str(technical_payload)}, ensure_ascii=False)

        vals = {
            'event_datetime': fields.Datetime.now(),
            'gestor_id': self.env.user.id,
            'action_type': action_type,
            'target_type': target_type,
            'summary': summary,
            'detail': detail or False,
            'usuario_id': usuario.id if usuario else False,
            'trabajador_id': trabajador.id if trabajador else False,
            'asignacion_id': asignacion.id if asignacion else False,
            'trabajo_fijo_id': trabajo_fijo.id if trabajo_fijo else False,
            'asignacion_mensual_id': asignacion_mensual.id if asignacion_mensual else False,
            'usuario_name': usuario_name or self.display_record_name(usuario),
            'trabajador_name': trabajador_name or self.display_record_name(trabajador),
            'usuario_grupo': usuario_grupo or (usuario.grupo if usuario else False),
            'target_label': target_label or False,
            'date_label': date_label or False,
            'month_label': month_label or False,
            'technical_payload': payload_text,
        }
        try:
            return self.sudo().with_context(portalgestor_allow_audit_create=True).create(vals)
        except Exception:
            _logger.exception("No se pudo crear el registro de auditoria de PortalGestor.")
            return False
