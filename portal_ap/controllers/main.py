# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.http import request


class PortalAPController(http.Controller):

    def _service(self, sudo=False):
        service = request.env['portal.ap.service']
        return service.sudo() if sudo else service

    def _get_today_year_month(self):
        today = fields.Date.context_today(request.env['portal.ap.service'])
        return today.year, today.month

    def _manager_scope(self):
        return request.env.user._get_gestor_management_scope()

    def _ensure_manager_access(self):
        return bool(self._manager_scope())

    def _get_session_worker(self):
        worker_id = request.session.get('portal_ap_trabajador_id')
        if not worker_id:
            return request.env['trabajadores.trabajador'].sudo().browse()

        worker = request.env['trabajadores.trabajador'].sudo().browse(int(worker_id)).exists()
        if not worker or worker.baja:
            request.session.pop('portal_ap_trabajador_id', None)
            return request.env['trabajadores.trabajador'].sudo().browse()
        return worker

    def _render_login(self, error=False, dni_nie=''):
        return request.render('portal_ap.login', {
            'error': error,
            'dni_nie': dni_nie or '',
        })

    @http.route(['/ap'], type='http', auth='public', methods=['GET'], sitemap=False)
    def portal_ap_login(self, **kwargs):
        if self._get_session_worker():
            return request.redirect('/ap/horario')
        return self._render_login()

    @http.route(['/ap/login'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def portal_ap_login_submit(self, **post):
        dni_nie = post.get('dni_nie') or ''
        worker, error_code = self._service(sudo=True)._find_worker_by_dni(dni_nie)
        if error_code:
            if error_code == 'duplicate':
                error = 'No se puede iniciar sesion con este DNI/NIE. Contacte con administracion.'
            else:
                error = 'No se ha encontrado ningun AP con ese DNI/NIE.'
            return self._render_login(error=error, dni_nie=dni_nie)

        request.session['portal_ap_trabajador_id'] = worker.id
        return request.redirect('/ap/horario')

    @http.route([
        '/ap/horario',
        '/ap/horario/<int:year>/<int:month>',
    ], type='http', auth='public', methods=['GET'], sitemap=False)
    def portal_ap_schedule(self, year=None, month=None, **kwargs):
        worker = self._get_session_worker()
        if not worker:
            return request.redirect('/ap')

        current_year, current_month = self._get_today_year_month()
        year = year or current_year
        month = month or current_month
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return request.redirect('/ap/horario/%s/%s' % (current_year, current_month))

        calendar_data = self._service(sudo=True)._get_worker_month_calendar(worker, year, month)
        calendar_data.update({
            'identity_caption': 'Horario AP',
            'identity_name': calendar_data['worker_name'],
            'header_action_kind': 'logout',
            'header_action_label': 'Salir',
            'header_action_url': '/ap/logout',
            'mobile_empty_label': 'Sin servicios',
        })
        return request.render('portal_ap.schedule', calendar_data)

    @http.route(['/ap/logout'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def portal_ap_logout(self, **post):
        request.session.pop('portal_ap_trabajador_id', None)
        return request.redirect('/ap')

    @http.route(['/consultar-horario'], type='http', auth='user', methods=['GET'], sitemap=False)
    def manager_schedule_index(self, search=None, **kwargs):
        if not self._ensure_manager_access():
            return request.redirect('/odoo')

        search = (search or '').strip()
        user_cards = self._service(sudo=True)._get_manager_user_cards(
            viewer=request.env.user,
            search=search,
        )
        return request.render('portal_ap.manager_user_list', {
            'search': search,
            'user_cards': user_cards,
        })

    @http.route([
        '/consultar-horario/usuario/<int:user_id>',
        '/consultar-horario/usuario/<int:user_id>/<int:year>/<int:month>',
    ], type='http', auth='user', methods=['GET'], sitemap=False)
    def manager_user_schedule(self, user_id, year=None, month=None, **kwargs):
        if not self._ensure_manager_access():
            return request.redirect('/odoo')

        Usuario = request.env['usuarios.usuario'].sudo().with_context(
            portalgestor_viewer_uid=request.env.user.id,
        )
        usuario = Usuario.search([
            ('id', '=', user_id),
            ('has_ap_service', '=', True),
        ], limit=1)
        if not usuario:
            return request.redirect('/consultar-horario')

        current_year, current_month = self._get_today_year_month()
        year = year or current_year
        month = month or current_month
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return request.redirect(f'/consultar-horario/usuario/{usuario.id}/{current_year}/{current_month}')

        calendar_data = self._service(sudo=True)._get_user_month_calendar(
            usuario,
            year,
            month,
            viewer=request.env.user,
        )
        calendar_data.update({
            'identity_caption': 'Horario usuario',
            'identity_name': calendar_data['user_name'],
            'header_action_kind': 'link',
            'header_action_label': 'Volver',
            'header_action_url': '/consultar-horario',
            'mobile_empty_label': 'Sin servicios',
        })
        return request.render('portal_ap.schedule', calendar_data)
