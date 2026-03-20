# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


@tagged('-at_install', 'post_install')
class TestPortalGestorOptimizations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Centro',
            'code': 'ZONA_CENTRO_TEST',
        })
        cls.usuario_a = cls.env['usuarios.usuario'].create({
            'name': 'Usuario A',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
        })
        cls.usuario_b = cls.env['usuarios.usuario'].create({
            'name': 'Usuario B',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
        })

    @classmethod
    def _create_worker(cls, suffix):
        return cls.env['trabajadores.trabajador'].create({
            'name': f'Trabajador {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_assignment(cls, usuario, fecha, line_specs):
        return cls.env['portalgestor.asignacion'].create({
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

    @classmethod
    def _create_fixed_assignment(
        cls,
        usuario,
        fecha_inicio,
        fecha_fin,
        line_specs,
    ):
        return cls.env['portalgestor.asignacion.mensual'].create({
            'usuario_id': usuario.id,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'linea_fija_ids': [
                (
                    0,
                    0,
                    {
                        'hora_inicio': hora_inicio,
                        'hora_fin': hora_fin,
                        'trabajador_id': trabajador.id,
                    },
                )
                for hora_inicio, hora_fin, trabajador in line_specs
            ],
        })

    def test_action_verificar_detects_overlapping_assignments(self):
        fecha = fields.Date.to_date('2026-03-19')
        trabajador = self._create_worker('Solape')

        asignacion_existente = self._create_assignment(
            self.usuario_b,
            fecha,
            [(9.0, 12.0, trabajador)],
        )
        asignacion_actual = self._create_assignment(
            self.usuario_a,
            fecha,
            [(10.0, 11.0, trabajador)],
        )

        action = asignacion_actual.action_verificar_y_confirmar()

        self.assertEqual(action['res_model'], 'portalgestor.conflict.wizard')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.conflict_type, 'overlapping')
        self.assertEqual(wizard.linea_conflicto_id.id, asignacion_existente.lineas_ids.id)

    def test_action_verificar_keeps_same_day_warning(self):
        fecha = fields.Date.to_date('2026-03-20')
        trabajador = self._create_worker('Aviso')

        self._create_assignment(
            self.usuario_b,
            fecha,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_actual = self._create_assignment(
            self.usuario_a,
            fecha,
            [(10.0, 12.0, trabajador)],
        )

        action = asignacion_actual.action_verificar_y_confirmar()

        self.assertEqual(action['res_model'], 'portalgestor.conflict.wizard')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.conflict_type, 'info_same_day')
        self.assertIn(self.usuario_b.name, wizard.info_resumen)
        self.assertIn('08:00', wizard.info_resumen)
        self.assertIn('10:00', wizard.info_resumen)

    def test_get_assignment_markers_groups_dates_once(self):
        trabajador = self._create_worker('Markers')
        fecha_1 = fields.Date.to_date('2026-03-21')
        fecha_2 = fields.Date.to_date('2026-03-22')

        self._create_assignment(
            self.usuario_a,
            fecha_1,
            [
                (8.0, 10.0, trabajador),
                (10.0, 12.0, trabajador),
            ],
        )
        self._create_assignment(
            self.usuario_b,
            fecha_2,
            [(9.0, 11.0, trabajador)],
        )

        markers = self.env['trabajadores.vacacion'].get_assignment_markers(
            [trabajador.id],
            fields.Date.to_string(fields.Date.to_date('2026-03-01')),
            fields.Date.to_string(fields.Date.to_date('2026-03-31')),
        )

        self.assertEqual(
            markers,
            [
                {'id': 'portalgestor_workday_2026-03-21', 'date': '2026-03-21'},
                {'id': 'portalgestor_workday_2026-03-22', 'date': '2026-03-22'},
            ],
        )

    def test_worker_search_excludes_vacations_from_context(self):
        fecha = fields.Date.to_date('2026-03-23')
        trabajador_en_vacaciones = self._create_worker('Vacaciones')
        trabajador_disponible = self._create_worker('Disponible')

        self.env['trabajadores.vacacion'].create({
            'trabajador_id': trabajador_en_vacaciones.id,
            'date_start': fecha,
            'date_stop': fecha,
        })

        trabajadores = self.env['trabajadores.trabajador'].with_context(
            exclude_vacaciones_fecha=fields.Date.to_string(fecha)
        ).search(
            [('id', 'in', [trabajador_en_vacaciones.id, trabajador_disponible.id])],
            order='id',
        )

        self.assertEqual(trabajadores.ids, [trabajador_disponible.id])

    def test_assignment_line_rejects_hours_out_of_range(self):
        fecha = fields.Date.to_date('2026-03-24')
        trabajador = self._create_worker('Rango')

        with self.assertRaises(ValidationError):
            self._create_assignment(
                self.usuario_a,
                fecha,
                [(-1.0, 10.0, trabajador)],
            )

        with self.assertRaises(ValidationError):
            self._create_assignment(
                self.usuario_a,
                fecha,
                [(8.0, 24.0, trabajador)],
            )

        asignacion_valida = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 23.9833333333, trabajador)],
        )
        self.assertTrue(asignacion_valida)

    def test_assignment_line_rejects_end_before_start(self):
        fecha = fields.Date.to_date('2026-03-25')
        trabajador = self._create_worker('Orden')

        with self.assertRaises(ValidationError):
            self._create_assignment(
                self.usuario_a,
                fecha,
                [(12.0, 11.0, trabajador)],
            )

    def test_calendar_bucket_summary_returns_existing_types_ordered(self):
        fecha = fields.Date.to_date('2099-03-26')
        trabajador = self._create_worker('Buckets')
        usuario_c = self.env['usuarios.usuario'].create({
            'name': 'Usuario C',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
        })

        self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, None)],
        )
        self._create_assignment(
            self.usuario_b,
            fecha,
            [
                (10.0, 12.0, trabajador),
                (12.0, 14.0, None),
            ],
        )
        self._create_assignment(
            usuario_c,
            fecha,
            [(14.0, 16.0, trabajador)],
        )

        buckets = self.env['portalgestor.asignacion'].get_calendar_bucket_summary(
            fields.Date.to_string(fecha),
            fields.Date.to_string(fecha),
        )

        self.assertEqual(
            [(bucket['bucket_type'], bucket['title']) for bucket in buckets],
            [
                ('pending', 'Por asignar [1]'),
                ('missing', 'Faltantes [1]'),
                ('completed', 'Completados [1]'),
            ],
        )

    def test_calendar_bucket_records_returns_only_matching_status(self):
        fecha = fields.Date.to_date('2099-03-27')
        trabajador = self._create_worker('Dialogo')

        self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, trabajador)],
        )
        self._create_assignment(
            self.usuario_b,
            fecha,
            [(10.0, 12.0, trabajador)],
        )

        records = self.env['portalgestor.asignacion'].get_calendar_bucket_records(
            fields.Date.to_string(fecha),
            'completed',
        )

        self.assertEqual(
            [record['name'] for record in records],
            [self.usuario_a.name, self.usuario_b.name],
        )

    def test_calendar_bucket_type_tracks_line_assignment_state(self):
        fecha = fields.Date.to_date('2099-04-01')
        trabajador = self._create_worker('Projection')

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, None)],
        )

        self.assertEqual(asignacion.calendar_bucket_type, 'pending')
        self.assertEqual(asignacion.color_calendario, 10)

        asignacion.lineas_ids.write({'trabajador_id': trabajador.id})
        self.assertEqual(asignacion.calendar_bucket_type, 'completed')
        self.assertEqual(asignacion.color_calendario, 1)

        self.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': asignacion.id,
            'hora_inicio': 10.0,
            'hora_fin': 12.0,
            'trabajador_id': False,
        })
        self.assertEqual(asignacion.calendar_bucket_type, 'missing')
        self.assertEqual(asignacion.color_calendario, 3)

    def test_calendar_bucket_summary_ignores_stale_stored_color(self):
        fecha = fields.Date.to_date('2099-03-30')
        trabajador = self._create_worker('Color Stale Summary')

        asignacion_pending = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, None)],
        )
        asignacion_completed = self._create_assignment(
            self.usuario_b,
            fecha,
            [(10.0, 12.0, trabajador)],
        )

        self.env.cr.execute(
            """
                UPDATE portalgestor_asignacion
                   SET color_calendario = NULL
                 WHERE id IN %s
            """,
            [tuple((asignacion_pending | asignacion_completed).ids)],
        )
        self.env['portalgestor.asignacion'].invalidate_model(['color_calendario'])

        buckets = self.env['portalgestor.asignacion'].get_calendar_bucket_summary(
            fields.Date.to_string(fecha),
            fields.Date.to_string(fecha),
        )

        self.assertEqual(
            [(bucket['bucket_type'], bucket['title']) for bucket in buckets],
            [
                ('pending', 'Por asignar [1]'),
                ('completed', 'Completados [1]'),
            ],
        )

    def test_calendar_bucket_records_ignores_stale_stored_color(self):
        fecha = fields.Date.to_date('2099-03-31')
        trabajador = self._create_worker('Color Stale Records')

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, trabajador)],
        )

        self.env.cr.execute(
            """
                UPDATE portalgestor_asignacion
                   SET color_calendario = NULL
                 WHERE id = %s
            """,
            [asignacion.id],
        )
        self.env['portalgestor.asignacion'].invalidate_model(['color_calendario'])

        records = self.env['portalgestor.asignacion'].get_calendar_bucket_records(
            fields.Date.to_string(fecha),
            'completed',
        )

        self.assertEqual(
            [record['id'] for record in records],
            [asignacion.id],
        )

    def test_worker_calendar_filter_search_matches_any_line_worker(self):
        fecha = fields.Date.to_date('2099-03-28')
        trabajador_1 = self._create_worker('Filtro 1')
        trabajador_2 = self._create_worker('Filtro 2')

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha,
            [
                (8.0, 10.0, trabajador_1),
                (10.0, 12.0, trabajador_2),
            ],
        )

        resultado = self.env['portalgestor.asignacion'].search(
            [('trabajador_calendar_filter_id', 'in', [trabajador_2.id])]
        )

        self.assertEqual(resultado, asignacion)

    def test_list_summary_fields_do_not_change_calendar_name(self):
        fecha = fields.Date.to_date('2026-03-29')
        trabajador_1 = self._create_worker('Lista 1')
        trabajador_2 = self._create_worker('Lista 2')

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha,
            [
                (8.0, 10.0, trabajador_1),
                (10.0, 12.0, trabajador_2),
            ],
        )

        self.assertEqual(asignacion.name, self.usuario_a.name)
        self.assertEqual(
            asignacion.trabajador_resumen,
            f'{trabajador_1.name} | {trabajador_2.name}',
        )
        self.assertEqual(
            asignacion.rango_horas_resumen,
            '08:00 - 10:00 | 10:00 - 12:00',
        )

        list_arch = self.env.ref('portalGestor.portalgestor_asignacion_list').arch_db
        calendar_arch = self.env.ref('portalGestor.portalgestor_asignacion_calendar').arch_db
        self.assertIn('trabajador_resumen', list_arch)
        self.assertIn('rango_horas_resumen', list_arch)
        self.assertIn('<field name="usuario_id"', calendar_arch)
        self.assertIn('portalgestor.asignacion.calendar.usuario.filter', calendar_arch)
        self.assertIn('portalgestor.asignacion.calendar.trabajador.filter', calendar_arch)
        self.assertIn('<field name="trabajador_id" invisible="1"', calendar_arch)
        self.assertNotIn('trabajador_resumen', calendar_arch)

    def test_assignment_create_sends_single_calendar_notification(self):
        fecha = fields.Date.to_date('2099-04-02')
        trabajador = self._create_worker('Bus Create')

        with patch.object(type(self.env['bus.bus']), '_sendone', autospec=True) as mock_sendone:
            asignacion = self._create_assignment(
                self.usuario_a,
                fecha,
                [(8.0, 10.0, trabajador)],
            )

        self.assertEqual(mock_sendone.call_count, 1)
        __self, channel, notification_type, payload = mock_sendone.call_args.args
        self.assertEqual(channel, 'portalgestor.calendar')
        self.assertEqual(notification_type, 'portalgestor.calendar.updated')
        self.assertEqual(payload['action_kind'], 'create')
        self.assertEqual(payload['assignment_ids'], [asignacion.id])
        self.assertEqual(payload['changed_dates'], [fields.Date.to_string(fecha)])
        self.assertEqual(payload['bucket_types'], ['completed'])

    def test_assignment_write_notifies_old_and_new_dates(self):
        fecha_inicial = fields.Date.to_date('2099-04-03')
        fecha_nueva = fields.Date.to_date('2099-04-04')
        trabajador = self._create_worker('Bus Move')

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha_inicial,
            [(8.0, 10.0, trabajador)],
        )

        with patch.object(type(self.env['bus.bus']), '_sendone', autospec=True) as mock_sendone:
            asignacion.write({'fecha': fecha_nueva})

        self.assertEqual(mock_sendone.call_count, 1)
        payload = mock_sendone.call_args.args[3]
        self.assertEqual(payload['action_kind'], 'write')
        self.assertEqual(payload['assignment_ids'], [asignacion.id])
        self.assertEqual(
            payload['changed_dates'],
            [
                fields.Date.to_string(fecha_inicial),
                fields.Date.to_string(fecha_nueva),
            ],
        )
        self.assertEqual(payload['bucket_types'], ['completed'])

    def test_assignment_line_write_notifies_bucket_transition(self):
        fecha = fields.Date.to_date('2099-04-05')
        trabajador = self._create_worker('Bus Transition')

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, trabajador)],
        )

        with patch.object(type(self.env['bus.bus']), '_sendone', autospec=True) as mock_sendone:
            asignacion.lineas_ids.write({'trabajador_id': False})

        self.assertEqual(mock_sendone.call_count, 1)
        payload = mock_sendone.call_args.args[3]
        self.assertEqual(payload['action_kind'], 'write')
        self.assertEqual(payload['assignment_ids'], [asignacion.id])
        self.assertEqual(payload['changed_dates'], [fields.Date.to_string(fecha)])
        self.assertEqual(payload['bucket_types'], ['pending', 'completed'])

    def test_worker_baja_releases_assignments_from_today_forward_only(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        ayer = hoy - timedelta(days=1)
        manana = hoy + timedelta(days=1)
        trabajador_baja = self._create_worker('Baja Trabajador')
        trabajador_activo = self._create_worker('Activo Soporte')

        asignacion_pasada = self._create_assignment(
            self.usuario_a,
            ayer,
            [(8.0, 10.0, trabajador_baja)],
        )
        asignacion_hoy = self._create_assignment(
            self.usuario_b,
            hoy,
            [
                (8.0, 10.0, trabajador_baja),
                (10.0, 12.0, trabajador_activo),
            ],
        )
        asignacion_futura = self._create_assignment(
            self.usuario_a,
            manana,
            [(8.0, 10.0, trabajador_baja)],
        )

        trabajador_baja.write({'baja': True})

        lineas_hoy = asignacion_hoy.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
        self.assertEqual(asignacion_pasada.lineas_ids.trabajador_id, trabajador_baja)
        self.assertFalse(lineas_hoy[0].trabajador_id)
        self.assertEqual(lineas_hoy[1].trabajador_id, trabajador_activo)
        self.assertEqual(asignacion_hoy.calendar_bucket_type, 'missing')
        self.assertFalse(asignacion_futura.lineas_ids.trabajador_id)
        self.assertEqual(asignacion_futura.calendar_bucket_type, 'pending')

    def test_user_baja_cancels_assignments_from_today_forward_only(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        ayer = hoy - timedelta(days=1)
        manana = hoy + timedelta(days=1)
        trabajador = self._create_worker('Baja Usuario')

        asignacion_pasada = self._create_assignment(
            self.usuario_a,
            ayer,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_hoy = self._create_assignment(
            self.usuario_a,
            hoy,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_futura = self._create_assignment(
            self.usuario_a,
            manana,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_otro_usuario = self._create_assignment(
            self.usuario_b,
            manana,
            [(10.0, 12.0, trabajador)],
        )

        self.usuario_a.write({'baja': True})

        self.assertTrue(asignacion_pasada.exists())
        self.assertFalse(asignacion_hoy.exists())
        self.assertFalse(asignacion_futura.exists())
        self.assertTrue(asignacion_otro_usuario.exists())

    def test_fixed_assignment_generates_individual_daily_assignments(self):
        trabajador_1 = self._create_worker('Fijo 1')
        trabajador_2 = self._create_worker('Fijo 2')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fields.Date.to_date('2099-04-01'),
            fields.Date.to_date('2099-04-03'),
            [
                (0.0, 2.0, trabajador_1),
                (15.0, 17.0, trabajador_2),
            ],
        )

        asignaciones = self.env['portalgestor.asignacion'].search(
            [
                ('usuario_id', '=', self.usuario_a.id),
                ('fecha', '>=', fields.Date.to_date('2099-04-01')),
                ('fecha', '<=', fields.Date.to_date('2099-04-03')),
            ],
            order='fecha',
        )

        self.assertEqual(
            asignaciones.mapped('fecha'),
            [
                fields.Date.to_date('2099-04-01'),
                fields.Date.to_date('2099-04-02'),
                fields.Date.to_date('2099-04-03'),
            ],
        )
        self.assertEqual(trabajo_fijo.total_dias_generados, 3)
        self.assertEqual(trabajo_fijo.total_lineas_generadas, 6)
        self.assertEqual(
            set(trabajo_fijo.asignacion_linea_ids.mapped('asignacion_mensual_id').ids),
            {trabajo_fijo.id},
        )
        self.assertEqual(
            set(trabajo_fijo.asignacion_linea_ids.mapped('asignacion_mensual_linea_id').ids),
            set(trabajo_fijo.linea_fija_ids.ids),
        )
        for asignacion in asignaciones:
            lineas = asignacion.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
            self.assertEqual(
                [
                    (linea.hora_inicio, linea.hora_fin, linea.trabajador_id.id)
                    for linea in lineas
                ],
                [
                    (0.0, 2.0, trabajador_1.id),
                    (15.0, 17.0, trabajador_2.id),
                ],
            )

    def test_fixed_assignment_write_updates_generated_dates_and_lines(self):
        trabajador_1 = self._create_worker('Fijo Write 1')
        trabajador_2 = self._create_worker('Fijo Write 2')
        trabajador_3 = self._create_worker('Fijo Write 3')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fields.Date.to_date('2099-05-10'),
            fields.Date.to_date('2099-05-11'),
            [
                (8.0, 10.0, trabajador_1),
                (15.0, 17.0, trabajador_2),
            ],
        )

        linea_1, linea_2 = trabajo_fijo.linea_fija_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
        trabajo_fijo.write({
            'fecha_fin': fields.Date.to_date('2099-05-12'),
            'linea_fija_ids': [
                (1, linea_1.id, {
                    'hora_inicio': 7.0,
                    'hora_fin': 9.0,
                    'trabajador_id': trabajador_3.id,
                }),
                (1, linea_2.id, {
                    'hora_inicio': 16.0,
                    'hora_fin': 18.0,
                }),
            ],
        })

        asignaciones = self.env['portalgestor.asignacion'].search(
            [
                ('usuario_id', '=', self.usuario_a.id),
                ('fecha', '>=', fields.Date.to_date('2099-05-10')),
                ('fecha', '<=', fields.Date.to_date('2099-05-12')),
            ],
            order='fecha',
        )

        self.assertEqual(trabajo_fijo.total_dias_generados, 3)
        self.assertEqual(trabajo_fijo.total_lineas_generadas, 6)
        self.assertEqual(
            asignaciones.mapped('fecha'),
            [
                fields.Date.to_date('2099-05-10'),
                fields.Date.to_date('2099-05-11'),
                fields.Date.to_date('2099-05-12'),
            ],
        )
        for asignacion in asignaciones:
            lineas = asignacion.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
            self.assertEqual(
                [
                    (linea.hora_inicio, linea.hora_fin, linea.trabajador_id.id)
                    for linea in lineas
                ],
                [
                    (7.0, 9.0, trabajador_3.id),
                    (16.0, 18.0, trabajador_2.id),
                ],
            )

    def test_fixed_assignment_unlink_cleans_empty_calendar_days(self):
        trabajador = self._create_worker('Fijo Unlink')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fields.Date.to_date('2099-06-01'),
            fields.Date.to_date('2099-06-02'),
            [(9.0, 11.0, trabajador)],
        )

        asignaciones = trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id')
        self.assertEqual(len(asignaciones), 2)

        trabajo_fijo.unlink()

        self.assertFalse(asignaciones.exists())
        self.assertFalse(
            self.env['portalgestor.asignacion'].search([
                ('usuario_id', '=', self.usuario_a.id),
                ('fecha', 'in', [
                    fields.Date.to_date('2099-06-01'),
                    fields.Date.to_date('2099-06-02'),
                ]),
            ])
        )

    def test_worker_baja_keeps_fixed_assignments_completed(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        manana = hoy + timedelta(days=1)
        trabajador = self._create_worker('Fijo Baja')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            hoy,
            manana,
            [(8.0, 10.0, trabajador)],
        )

        trabajador.write({'baja': True})

        self.assertEqual(
            set(trabajo_fijo.asignacion_linea_ids.mapped('trabajador_id').ids),
            {trabajador.id},
        )
        for asignacion in trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id'):
            self.assertEqual(asignacion.calendar_bucket_type, 'completed')
