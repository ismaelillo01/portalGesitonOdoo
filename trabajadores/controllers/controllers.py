# -*- coding: utf-8 -*-
# from odoo import http


# class Trabajadores(http.Controller):
#     @http.route('/trabajadores/trabajadores', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/trabajadores/trabajadores/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('trabajadores.listing', {
#             'root': '/trabajadores/trabajadores',
#             'objects': http.request.env['trabajadores.trabajadores'].search([]),
#         })

#     @http.route('/trabajadores/trabajadores/objects/<model("trabajadores.trabajadores"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('trabajadores.object', {
#             'object': obj
#         })

