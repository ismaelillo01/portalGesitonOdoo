# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import Response, request


class PortalAPMobileAPIController(http.Controller):

    def _json_body(self):
        payload = request.httprequest.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}

    def _json_response(self, payload, status=200):
        return Response(
            json.dumps(payload, ensure_ascii=False, default=str),
            status=status,
            content_type='application/json; charset=utf-8',
        )

    def _service(self):
        return request.env['portal.ap.service'].sudo()

    def _session_token(self, payload=None):
        payload = payload or {}
        auth_header = request.httprequest.headers.get('Authorization') or ''
        if auth_header.lower().startswith('bearer '):
            return auth_header[7:].strip()
        return (
            request.httprequest.headers.get('X-AP-Session')
            or payload.get('session_token')
            or request.params.get('session_token')
            or ''
        )

    @http.route('/api/ap/login', type='http', auth='public', methods=['POST'], csrf=False, cors='*', sitemap=False)
    def mobile_login(self, **kwargs):
        payload = self._json_body()
        response = self._service()._mobile_login(
            dni_nie=payload.get('dni_nie') or payload.get('dni') or '',
            device_id=payload.get('device_id') or '',
            device_label=payload.get('device_label') or '',
        )
        return self._json_response(response, status=200 if response.get('ok') else 401)

    @http.route('/api/ap/schedule', type='http', auth='public', methods=['GET'], csrf=False, cors='*', sitemap=False)
    def mobile_schedule(self, **kwargs):
        response = self._service()._mobile_schedule(
            session_token=self._session_token(),
            month=request.params.get('month') or '',
        )
        return self._json_response(response, status=200 if response.get('ok') else 401)

    @http.route('/api/ap/check', type='http', auth='public', methods=['POST'], csrf=False, cors='*', sitemap=False)
    def mobile_check(self, **kwargs):
        payload = self._json_body()
        response = self._service()._mobile_check(
            session_token=self._session_token(payload),
            payload=payload,
        )
        return self._json_response(response, status=200 if response.get('ok') else 400)

    @http.route('/api/ap/sync', type='http', auth='public', methods=['POST'], csrf=False, cors='*', sitemap=False)
    def mobile_sync(self, **kwargs):
        payload = self._json_body()
        response = self._service()._mobile_sync(
            session_token=self._session_token(payload),
            events=payload.get('events') or [],
        )
        return self._json_response(response, status=200 if response.get('ok') else 400)
