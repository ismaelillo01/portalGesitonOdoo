# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta, timezone
import re
import secrets
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PortalAPMobileSession(models.Model):
    _name = 'portal.ap.mobile.session'
    _description = 'Sesion movil Portal AP'
    _order = 'last_seen_at desc, id desc'

    token = fields.Char(required=True, index=True, copy=False)
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        ondelete='cascade',
        index=True,
    )
    active = fields.Boolean(default=True, index=True)
    device_id = fields.Char(index=True)
    device_label = fields.Char()
    created_at = fields.Datetime(default=fields.Datetime.now, required=True)
    last_seen_at = fields.Datetime(default=fields.Datetime.now, required=True)

    _sql_constraints = [
        ('portal_ap_mobile_session_token_uniq', 'unique(token)', 'El token de sesion movil debe ser unico.'),
    ]

    @api.model
    def _new_token(self):
        for __attempt in range(10):
            token = secrets.token_urlsafe(32)
            if not self.sudo().search_count([('token', '=', token)]):
                return token
        raise ValidationError(_('No se pudo generar un token de sesion movil unico.'))


class PortalAPFichaje(models.Model):
    _name = 'portal.ap.fichaje'
    _description = 'Fichaje movil AP'
    _order = 'server_datetime desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    trabajador_id = fields.Many2one('trabajadores.trabajador', string='AP', ondelete='set null', index=True)
    usuario_id = fields.Many2one('usuarios.usuario', string='Usuario', ondelete='set null', index=True)
    assignment_line_id = fields.Many2one(
        'portalgestor.asignacion.linea',
        string='Tramo planificado',
        ondelete='set null',
        index=True,
    )
    assignment_date = fields.Date(related='assignment_line_id.fecha', string='Fecha planificada', store=True)
    planned_start = fields.Float(related='assignment_line_id.hora_inicio', string='Hora inicio planificada', store=True)
    planned_end = fields.Float(related='assignment_line_id.hora_fin', string='Hora fin planificada', store=True)
    event_type = fields.Selection([
        ('in', 'Entrada'),
        ('out', 'Salida'),
    ], string='Tipo', required=True, index=True)
    server_datetime = fields.Datetime(string='Hora servidor', default=fields.Datetime.now, required=True, index=True)
    client_datetime = fields.Char(string='Hora dispositivo')
    client_event_id = fields.Char(string='ID evento dispositivo', required=True, copy=False, index=True)
    qr_token_snapshot = fields.Char(string='QR recibido', copy=False)
    latitude = fields.Float(string='Latitud', digits=(16, 8))
    longitude = fields.Float(string='Longitud', digits=(16, 8))
    accuracy = fields.Float(string='Precision GPS')
    device_id = fields.Char(string='ID dispositivo', index=True)
    device_label = fields.Char(string='Dispositivo')
    origin = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline sincronizado'),
    ], string='Origen', default='online', required=True, index=True)
    state = fields.Selection([
        ('valid', 'Valido'),
        ('pending', 'Pendiente'),
        ('warning', 'Con incidencia'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='valid', required=True, index=True)
    incidence = fields.Text(string='Incidencia')

    _sql_constraints = [
        ('portal_ap_fichaje_client_event_uniq', 'unique(client_event_id)', 'El evento movil ya fue registrado.'),
    ]

    @api.depends('trabajador_id', 'usuario_id', 'event_type', 'server_datetime', 'state')
    def _compute_name(self):
        labels = dict(self._fields['event_type'].selection)
        for record in self:
            record.name = '%s - %s - %s' % (
                labels.get(record.event_type, record.event_type or ''),
                record.trabajador_id.display_name or _('AP'),
                fields.Datetime.to_string(record.server_datetime) if record.server_datetime else '',
            )


class UsuarioPortalAPQR(models.Model):
    _inherit = 'usuarios.usuario'

    portal_ap_qr_token = fields.Char(string='Token QR AP', copy=False, index=True, readonly=True)
    portal_ap_qr_generated_at = fields.Datetime(string='QR AP generado el', readonly=True, copy=False)
    portal_ap_qr_active = fields.Boolean(string='QR AP activo', default=True, copy=False)

    _sql_constraints = [
        ('usuarios_usuario_portal_ap_qr_token_uniq', 'unique(portal_ap_qr_token)', 'El token QR AP debe ser unico.'),
    ]

    @api.model
    def _new_portal_ap_qr_token(self):
        for __attempt in range(10):
            token = secrets.token_urlsafe(32)
            if not self.sudo().search_count([('portal_ap_qr_token', '=', token)]):
                return token
        raise ValidationError(_('No se pudo generar un token QR unico.'))

    def _ensure_portal_ap_qr_token(self):
        for record in self:
            if not record.portal_ap_qr_token:
                record.sudo().write({
                    'portal_ap_qr_token': self._new_portal_ap_qr_token(),
                    'portal_ap_qr_generated_at': fields.Datetime.now(),
                    'portal_ap_qr_active': True,
                })
        return True

    def action_portal_ap_regenerate_qr(self):
        for record in self:
            record.sudo().write({
                'portal_ap_qr_token': self._new_portal_ap_qr_token(),
                'portal_ap_qr_generated_at': fields.Datetime.now(),
                'portal_ap_qr_active': True,
            })
        return True

    def action_portal_ap_revoke_qr(self):
        self.sudo().write({'portal_ap_qr_active': False})
        return True

    def action_portal_ap_print_qr(self):
        self._ensure_portal_ap_qr_token()
        return self.env.ref('portal_ap.action_report_portal_ap_user_qr').report_action(self)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_portal_ap_qr_token()
        return records


class PortalAPServiceMobile(models.AbstractModel):
    _inherit = 'portal.ap.service'

    _MOBILE_TIME_TOLERANCE = timedelta(minutes=5)

    @api.model
    def _mobile_error(self, code, message):
        return {'ok': False, 'error': {'code': code, 'message': message}}

    @api.model
    def _mobile_month_bounds(self, month):
        month = (month or '').strip()
        if not re.match(r'^\d{4}-\d{2}$', month):
            today = fields.Date.context_today(self)
            month = '%04d-%02d' % (today.year, today.month)
        year, month_number = [int(part) for part in month.split('-')]
        month_start, month_end = self._get_month_bounds(year, month_number)
        return month, month_start, month_end

    @api.model
    def _mobile_get_session(self, token):
        token = (token or '').strip()
        if not token:
            return self.env['portal.ap.mobile.session'].sudo().browse(), self._mobile_error(
                'missing_session',
                _('Falta el token de sesion.'),
            )
        session = self.env['portal.ap.mobile.session'].sudo().search([
            ('token', '=', token),
            ('active', '=', True),
        ], limit=1)
        if not session or not session.trabajador_id or session.trabajador_id.baja:
            return self.env['portal.ap.mobile.session'].sudo().browse(), self._mobile_error(
                'invalid_session',
                _('Sesion movil no valida.'),
            )
        session.write({'last_seen_at': fields.Datetime.now()})
        return session, False

    @api.model
    def _mobile_login(self, dni_nie, device_id=None, device_label=None):
        worker, error_code = self._find_worker_by_dni(dni_nie)
        if error_code:
            if error_code == 'duplicate':
                return self._mobile_error(
                    'duplicate_dni',
                    _('No se puede iniciar sesion con este DNI/NIE. Contacte con administracion.'),
                )
            return self._mobile_error(
                'not_found',
                _('No se ha encontrado ningun AP activo con ese DNI/NIE.'),
            )

        Session = self.env['portal.ap.mobile.session'].sudo()
        session = Session.create({
            'token': Session._new_token(),
            'trabajador_id': worker.id,
            'device_id': device_id or '',
            'device_label': device_label or '',
            'last_seen_at': fields.Datetime.now(),
        })
        return {
            'ok': True,
            'session_token': session.token,
            'worker': self._mobile_worker_payload(worker),
            'config': {
                'qr_scope': 'usuarios.usuario',
                'gps_mode': 'informative',
                'offline_mode': 'queue',
            },
        }

    @api.model
    def _mobile_worker_payload(self, worker):
        return {
            'id': worker.id,
            'name': worker.display_name or worker.nombre_completo or worker.name,
            'dni_nie': worker.dni_nie or '',
        }

    @api.model
    def _mobile_shift_status(self, line):
        checks = self.env['portal.ap.fichaje'].sudo().search([
            ('assignment_line_id', '=', line.id),
            ('state', 'in', ['valid', 'warning', 'pending']),
        ], order='server_datetime desc, id desc')
        check_in = checks.filtered(lambda check: check.event_type == 'in')[:1]
        check_out = checks.filtered(lambda check: check.event_type == 'out')[:1]
        status = 'pending'
        if check_in and check_out:
            status = 'complete'
        elif check_in:
            status = 'in_progress'

        warnings = [
            check.incidence
            for check in checks
            if check.incidence and check.state in ('warning', 'pending')
        ]
        return {
            'status': status,
            'check_in_at': fields.Datetime.to_string(check_in.server_datetime) if check_in else False,
            'check_out_at': fields.Datetime.to_string(check_out.server_datetime) if check_out else False,
            'warnings': warnings,
        }

    @api.model
    def _mobile_schedule(self, session_token, month):
        session, error = self._mobile_get_session(session_token)
        if error:
            return error

        month_label, month_start, month_end = self._mobile_month_bounds(month)
        worker = session.trabajador_id
        lines = self.env['portalgestor.asignacion.linea'].sudo().search([
            ('trabajador_id', '=', worker.id),
            ('fecha', '>=', month_start),
            ('fecha', '<=', month_end),
            ('asignacion_id.confirmado', '=', True),
        ], order='fecha asc, hora_inicio asc, hora_fin asc, id asc')

        users = lines.mapped('asignacion_id.usuario_id')
        users._ensure_portal_ap_qr_token()
        user_view_data = self.env['usuarios.usuario'].sudo().get_portalgestor_user_view_data(users.ids)

        shifts = []
        for line in lines:
            usuario = line.asignacion_id.usuario_id
            status_payload = self._mobile_shift_status(line)
            shifts.append({
                'id': line.id,
                'date': fields.Date.to_string(line.fecha),
                'hora_inicio': line.hora_inicio,
                'hora_fin': line.hora_fin,
                'time_range': '%s - %s' % (
                    self._format_float_hour(line.hora_inicio),
                    self._format_float_hour(line.hora_fin),
                ),
                'usuario': {
                    'id': usuario.id,
                    'name': user_view_data.get(usuario.id, {}).get('display_name') or usuario.display_name or usuario.name,
                    'address': usuario.direccion or '',
                },
                'status': status_payload['status'],
                'check_in_at': status_payload['check_in_at'],
                'check_out_at': status_payload['check_out_at'],
                'warnings': status_payload['warnings'],
            })

        return {
            'ok': True,
            'worker': self._mobile_worker_payload(worker),
            'month': month_label,
            'shifts': shifts,
        }

    @api.model
    def _mobile_local_datetime_from_payload(self, payload, origin):
        if origin == 'offline' and payload.get('client_datetime'):
            raw_datetime = str(payload.get('client_datetime') or '').strip()
            try:
                parsed = datetime.fromisoformat(raw_datetime.replace('Z', '+00:00'))
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return fields.Datetime.context_timestamp(self, parsed)
            except (TypeError, ValueError):
                pass
        return fields.Datetime.context_timestamp(self, fields.Datetime.now())

    @api.model
    def _mobile_time_warning(self, line, local_datetime=None):
        local_datetime = local_datetime or fields.Datetime.context_timestamp(self, fields.Datetime.now())
        if getattr(local_datetime, 'tzinfo', None):
            local_datetime = local_datetime.replace(tzinfo=None)

        planned_date = fields.Date.to_date(line.fecha)
        planned_start = datetime.combine(planned_date, time.min) + timedelta(hours=line.hora_inicio)
        planned_end = datetime.combine(planned_date, time.min) + timedelta(hours=line.hora_fin)

        if (
            local_datetime < planned_start - self._MOBILE_TIME_TOLERANCE
            or local_datetime > planned_end + self._MOBILE_TIME_TOLERANCE
        ):
            return _('Fichaje fuera del rango horario planificado.')
        return False

    @api.model
    def _mobile_check(self, session_token, payload, force_origin=None):
        session, error = self._mobile_get_session(session_token)
        if error:
            return error

        payload = payload or {}
        client_event_id = (payload.get('client_event_id') or str(uuid.uuid4())).strip()
        existing = self.env['portal.ap.fichaje'].sudo().search([
            ('client_event_id', '=', client_event_id),
        ], limit=1)
        if existing:
            return self._mobile_check_response(existing)

        worker = session.trabajador_id
        event_type = (payload.get('event_type') or '').strip()
        if event_type not in ('in', 'out'):
            event_type = 'in'

        line = self.env['portalgestor.asignacion.linea'].sudo().browse(
            int(payload.get('assignment_line_id') or 0)
        ).exists()
        usuario = line.asignacion_id.usuario_id if line else self.env['usuarios.usuario'].sudo().browse()
        qr_token = (payload.get('qr_token') or '').strip()
        state = 'valid'
        incidences = []
        origin = force_origin or payload.get('origin') or 'online'
        if origin not in ('online', 'offline'):
            origin = 'online'

        if not line:
            state = 'rejected'
            incidences.append(_('El tramo planificado no existe.'))
        elif line.trabajador_id != worker or not line.asignacion_id.confirmado:
            state = 'rejected'
            incidences.append(_('El tramo no pertenece al AP autenticado o no esta confirmado.'))
        else:
            matched_user = self.env['usuarios.usuario'].sudo().search([
                ('portal_ap_qr_token', '=', qr_token),
                ('portal_ap_qr_active', '=', True),
            ], limit=1)
            if not matched_user or matched_user != usuario:
                state = 'rejected'
                incidences.append(_('El QR escaneado no corresponde al usuario del tramo.'))
            else:
                warning = self._mobile_time_warning(
                    line,
                    self._mobile_local_datetime_from_payload(payload, origin),
                )
                if warning:
                    state = 'warning'
                    incidences.append(warning)

        check = self.env['portal.ap.fichaje'].sudo().create({
            'trabajador_id': worker.id,
            'usuario_id': usuario.id if usuario else False,
            'assignment_line_id': line.id if line else False,
            'event_type': event_type,
            'client_datetime': payload.get('client_datetime') or '',
            'client_event_id': client_event_id,
            'qr_token_snapshot': qr_token,
            'latitude': payload.get('latitude') or 0.0,
            'longitude': payload.get('longitude') or 0.0,
            'accuracy': payload.get('accuracy') or 0.0,
            'device_id': payload.get('device_id') or session.device_id or '',
            'device_label': payload.get('device_label') or session.device_label or '',
            'origin': origin,
            'state': state,
            'incidence': '\n'.join(str(incidence) for incidence in incidences),
        })
        return self._mobile_check_response(check)

    @api.model
    def _mobile_check_response(self, check):
        shift_status = 'pending'
        if check.assignment_line_id and check.state != 'rejected':
            shift_status = self._mobile_shift_status(check.assignment_line_id)['status']
        return {
            'ok': check.state != 'rejected',
            'fichaje': {
                'id': check.id,
                'client_event_id': check.client_event_id,
                'event_type': check.event_type,
                'server_datetime': fields.Datetime.to_string(check.server_datetime),
                'state': check.state,
                'incidence': check.incidence or '',
            },
            'shift_status': shift_status,
            'error': {
                'code': 'rejected',
                'message': check.incidence or _('Fichaje rechazado.'),
            } if check.state == 'rejected' else False,
        }

    @api.model
    def _mobile_sync(self, session_token, events):
        results = []
        for event in events or []:
            event = dict(event)
            event['session_token'] = session_token
            results.append(self._mobile_check(session_token, event, force_origin='offline'))
        return {
            'ok': True,
            'results': results,
        }
