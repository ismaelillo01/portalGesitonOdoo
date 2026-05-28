# -*- coding: utf-8 -*-
import time

from odoo import fields, http
from odoo.http import request

# Session timeout: 8 hours in seconds
PORTAL_USUARIO_SESSION_TIMEOUT = 8 * 60 * 60


class PortalUsuarioController(http.Controller):

    def _service(self, sudo=False):
        service = request.env['portal.usuario.service']
        return service.sudo() if sudo else service

    def _get_today_year_month(self):
        today = fields.Date.context_today(request.env['portal.usuario.service'])
        return today.year, today.month

    def _get_session_usuario(self):
        usuario_id = request.session.get('portal_usuario_usuario_id')
        if not usuario_id:
            return request.env['usuarios.usuario'].sudo().browse()

        login_ts = request.session.get('portal_usuario_login_ts', 0)
        if time.time() - login_ts > PORTAL_USUARIO_SESSION_TIMEOUT:
            request.session.pop('portal_usuario_usuario_id', None)
            request.session.pop('portal_usuario_login_ts', None)
            return request.env['usuarios.usuario'].sudo().browse()

        usuario = request.env['usuarios.usuario'].sudo().browse(int(usuario_id)).exists()
        if not usuario or usuario.baja:
            request.session.pop('portal_usuario_usuario_id', None)
            request.session.pop('portal_usuario_login_ts', None)
            return request.env['usuarios.usuario'].sudo().browse()
        return usuario

    def _render_login(self, error=False, codigo=''):
        return request.render('portal_usuario.login', {
            'error': error,
            'codigo': codigo or '',
        })

    @http.route(['/usuario'], type='http', auth='public', methods=['GET'], sitemap=False)
    def portal_usuario_login(self, **kwargs):
        if self._get_session_usuario():
            return request.redirect('/usuario/horario')
        return self._render_login()

    @http.route(['/usuario/login'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def portal_usuario_login_submit(self, **post):
        codigo = post.get('codigo') or ''
        usuario, error_code = self._service(sudo=True)._find_usuario_by_codigo(codigo)
        if error_code:
            if error_code == 'duplicate':
                error = 'No se puede iniciar sesion con este codigo. Contacte con administracion.'
            elif error_code == 'no_ap_service':
                error = 'El usuario no tiene el servicio de Atencion Personal activo.'
            else:
                error = 'No se ha encontrado ningun usuario con ese codigo.'
            return self._render_login(error=error, codigo=codigo)

        request.session['portal_usuario_usuario_id'] = usuario.id
        request.session['portal_usuario_login_ts'] = time.time()
        return request.redirect('/usuario/horario')

    @http.route([
        '/usuario/horario',
        '/usuario/horario/<int:year>/<int:month>',
    ], type='http', auth='public', methods=['GET'], sitemap=False)
    def portal_usuario_schedule(self, year=None, month=None, **kwargs):
        usuario = self._get_session_usuario()
        if not usuario:
            return request.redirect('/usuario')

        current_year, current_month = self._get_today_year_month()
        year = year or current_year
        month = month or current_month
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return request.redirect('/usuario/horario/%s/%s' % (current_year, current_month))

        calendar_data = self._service(sudo=True)._get_usuario_month_calendar(usuario, year, month)
        calendar_data.update({
            'identity_caption': 'Mi Atencion',
            'identity_name': calendar_data['usuario_name'],
            'header_action_kind': 'logout',
            'header_action_label': 'Salir',
            'header_action_url': '/usuario/logout',
            'mobile_empty_label': 'Sin atencion programada',
        })
        return request.render('portal_usuario.schedule', calendar_data)

    @http.route(['/usuario/logout'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def portal_usuario_logout(self, **post):
        request.session.pop('portal_usuario_usuario_id', None)
        request.session.pop('portal_usuario_login_ts', None)
        return request.redirect('/usuario')
