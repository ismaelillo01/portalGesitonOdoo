# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorUserHoursSummary(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Resumen Horas AP',
            'code': 'ZONA_RESUMEN_HORAS_AP',
        })

    @classmethod
    def _create_user(cls, suffix):
        return cls.env['usuarios.usuario'].create({
            'name': f'Usuario Resumen {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })

    @classmethod
    def _create_worker(cls, suffix):
        return cls.env['trabajadores.trabajador'].create({
            'name': f'AP Resumen {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_assignment(cls, usuario, fecha, line_specs, confirmed=True):
        assignment = cls.env['portalgestor.asignacion'].create({
            'usuario_id': usuario.id,
            'fecha': fecha,
            'lineas_ids': [
                (
                    0,
                    0,
                    {
                        'hora_inicio': hora_inicio,
                        'hora_fin': hora_fin,
                        'trabajador_id': trabajador.id if trabajador else False,
                    },
                )
                for hora_inicio, hora_fin, trabajador in line_specs
            ],
        })
        if confirmed:
            assignment.write({'confirmado': True})
        return assignment

    @classmethod
    def _create_verified_absence(cls, trabajador, fecha, hora_inicio, hora_fin, motivo='Falta justificada'):
        absence = cls.env['trabajadores.falta.justificada'].create({
            'trabajador_id': trabajador.id,
            'fecha': fecha,
            'hora_inicio': hora_inicio,
            'hora_fin': hora_fin,
            'motivo': motivo,
        })
        absence.action_verificar()
        return absence

    def _get_summary(self, usuario, start='2026-03-01', end='2026-03-31'):
        return self.env['portalgestor.asignacion'].get_user_month_ap_hours_summary(
            usuario.id,
            start,
            end,
        )

    def test_summary_groups_hours_by_ap_and_total(self):
        usuario = self._create_user('Agrupado')
        ap_1 = self._create_worker('Agrupado A')
        ap_2 = self._create_worker('Agrupado B')
        self._create_assignment(
            usuario,
            fields.Date.to_date('2026-03-04'),
            [(8.0, 10.0, ap_1), (10.0, 12.0, ap_2)],
        )
        self._create_assignment(
            usuario,
            fields.Date.to_date('2026-03-05'),
            [(9.0, 10.0, ap_1)],
        )

        summary = self._get_summary(usuario)
        by_ap = {ap['id']: ap for ap in summary['aps']}

        self.assertEqual(summary['total_minutes'], 300)
        self.assertEqual(by_ap[ap_1.id]['minutes'], 180)
        self.assertEqual(by_ap[ap_2.id]['minutes'], 120)
        self.assertEqual(summary['total_label'], '5h')

    def test_unassigned_lines_are_not_computable(self):
        usuario = self._create_user('Sin AP')
        ap = self._create_worker('Sin AP')
        self._create_assignment(
            usuario,
            fields.Date.to_date('2026-03-06'),
            [(8.0, 10.0, None), (10.0, 12.0, ap)],
        )

        summary = self._get_summary(usuario)

        self.assertEqual(summary['total_minutes'], 120)
        self.assertEqual(summary['unassigned_minutes'], 120)
        self.assertEqual(summary['aps'][0]['id'], ap.id)

    def test_partial_justified_absence_reduces_computable_and_reports_incident(self):
        usuario = self._create_user('Falta Parcial')
        ap = self._create_worker('Falta Parcial')
        fecha = fields.Date.to_date('2026-03-07')
        self._create_assignment(usuario, fecha, [(8.0, 12.0, ap)])
        self._create_verified_absence(ap, fecha, 9.0, 10.0, motivo='Consulta medica')

        summary = self._get_summary(usuario)
        ap_summary = summary['aps'][0]

        self.assertEqual(summary['total_minutes'], 180)
        self.assertEqual(ap_summary['minutes'], 180)
        self.assertEqual(ap_summary['justified_minutes'], 60)
        self.assertEqual(ap_summary['incidents'][0]['reason'], 'Consulta medica')

    def test_full_justified_absence_keeps_ap_with_zero_computable(self):
        usuario = self._create_user('Falta Completa')
        ap = self._create_worker('Falta Completa')
        fecha = fields.Date.to_date('2026-03-08')
        self._create_assignment(usuario, fecha, [(8.0, 10.0, ap)])
        self._create_verified_absence(ap, fecha, 8.0, 10.0, motivo='Permiso')

        summary = self._get_summary(usuario)
        ap_summary = summary['aps'][0]

        self.assertEqual(summary['total_minutes'], 0)
        self.assertEqual(ap_summary['id'], ap.id)
        self.assertEqual(ap_summary['minutes'], 0)
        self.assertEqual(ap_summary['justified_minutes'], 120)

    def test_summary_ignores_other_month_unconfirmed_and_other_user(self):
        usuario = self._create_user('Filtro')
        other_user = self._create_user('Filtro Otro')
        ap = self._create_worker('Filtro')
        self._create_assignment(usuario, fields.Date.to_date('2026-03-09'), [(8.0, 9.0, ap)])
        self._create_assignment(usuario, fields.Date.to_date('2026-04-09'), [(8.0, 9.0, ap)])
        self._create_assignment(usuario, fields.Date.to_date('2026-03-10'), [(8.0, 9.0, ap)], confirmed=False)
        self._create_assignment(other_user, fields.Date.to_date('2026-03-09'), [(8.0, 9.0, ap)])

        summary = self._get_summary(usuario)

        self.assertEqual(summary['total_minutes'], 60)
        self.assertEqual(summary['aps'][0]['minutes'], 60)
