# -*- coding: utf-8 -*-
# from odoo import http


# class Gestores(http.Controller):
#     @http.route('/gestores/gestores', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/gestores/gestores/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('gestores.listing', {
#             'root': '/gestores/gestores',
#             'objects': http.request.env['gestores.gestores'].search([]),
#         })

#     @http.route('/gestores/gestores/objects/<model("gestores.gestores"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('gestores.object', {
#             'object': obj
#         })

