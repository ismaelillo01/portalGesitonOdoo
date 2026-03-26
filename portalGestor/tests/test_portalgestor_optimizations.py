# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
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
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Centro',
            'code': 'ZONA_CENTRO_TEST',
        })
        cls.usuario_a = cls.env['usuarios.usuario'].create({
            'name': 'Usuario A',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario_b = cls.env['usuarios.usuario'].create({
            'name': 'Usuario B',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
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

    def test_vacation_rejects_days_with_existing_assignments(self):
        fecha = fields.Date.to_date('2026-03-24')
        trabajador = self._create_worker('Vacacion Con Trabajo')

        self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 12.0, trabajador)],
        )

        with self.assertRaises(ValidationError) as error:
            self.env['trabajadores.vacacion'].create({
                'trabajador_id': trabajador.id,
                'date_start': fecha,
                'date_stop': fecha,
            })

        self.assertIn('2026-03-24', str(error.exception))

    def test_vacation_rejects_days_with_existing_fixed_assignments(self):
        fecha_inicio = fields.Date.to_date('2026-03-25')
        fecha_fin = fields.Date.to_date('2026-03-27')
        trabajador = self._create_worker('Vacacion Fijo')

        self._create_fixed_assignment(
            self.usuario_a,
            fecha_inicio,
            fecha_fin,
            [(9.0, 11.0, trabajador)],
        )

        with self.assertRaises(ValidationError):
            self.env['trabajadores.vacacion'].create({
                'trabajador_id': trabajador.id,
                'date_start': fields.Date.to_date('2026-03-26'),
                'date_stop': fields.Date.to_date('2026-03-26'),
            })

    def test_vacation_rejects_overlapping_ranges_for_same_worker(self):
        trabajador = self._create_worker('Solape Vacacion')

        self.env['trabajadores.vacacion'].create({
            'trabajador_id': trabajador.id,
            'date_start': fields.Date.to_date('2026-04-01'),
            'date_stop': fields.Date.to_date('2026-04-03'),
        })

        with self.assertRaises(ValidationError):
            self.env['trabajadores.vacacion'].create({
                'trabajador_id': trabajador.id,
                'date_start': fields.Date.to_date('2026-04-03'),
                'date_stop': fields.Date.to_date('2026-04-05'),
            })

    def test_vacation_rejects_workers_on_baja(self):
        trabajador = self._create_worker('Baja Vacacion')
        trabajador.write({'baja': True})

        with self.assertRaises(ValidationError):
            self.env['trabajadores.vacacion'].create({
                'trabajador_id': trabajador.id,
                'date_start': fields.Date.to_date('2026-04-10'),
                'date_stop': fields.Date.to_date('2026-04-10'),
            })

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
            'servicio_ids': [(6, 0, [self.ap_service.id])],
        })

        asignacion_a = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, None)],
        )
        asignacion_b = self._create_assignment(
            self.usuario_b,
            fecha,
            [
                (10.0, 12.0, trabajador),
                (12.0, 14.0, None),
            ],
        )
        asignacion_c = self._create_assignment(
            usuario_c,
            fecha,
            [(14.0, 16.0, trabajador)],
        )
        (asignacion_a | asignacion_b | asignacion_c).write({'confirmado': True})

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

        asignacion_a = self._create_assignment(
            self.usuario_a,
            fecha,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_b = self._create_assignment(
            self.usuario_b,
            fecha,
            [(10.0, 12.0, trabajador)],
        )
        (asignacion_a | asignacion_b).write({'confirmado': True})

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
        (asignacion_pending | asignacion_completed).write({'confirmado': True})

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
        asignacion.write({'confirmado': True})

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
            self.assertEqual(mock_sendone.call_count, 0)
            asignacion.write({'confirmado': True})

        self.assertEqual(mock_sendone.call_count, 1)
        __self, channel, notification_type, payload = mock_sendone.call_args.args
        self.assertEqual(channel, 'portalgestor.calendar')
        self.assertEqual(notification_type, 'portalgestor.calendar.updated')
        self.assertEqual(payload['action_kind'], 'write')
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
        asignacion.write({'confirmado': True})

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
        asignacion.write({'confirmado': True})

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

        trabajador_baja.with_context(
            portalgestor_cutoff_datetime=datetime.combine(hoy, datetime.min.time()),
        ).write({'baja': True})

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

        self.usuario_a.with_context(
            portalgestor_cutoff_datetime=datetime.combine(hoy, datetime.min.time()),
        ).write({'baja': True})

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

    def test_fixed_assignment_verification_confirms_generated_days(self):
        trabajador = self._create_worker('Fijo Verificar OK')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fields.Date.to_date('2099-05-20'),
            fields.Date.to_date('2099-05-21'),
            [(8.0, 10.0, trabajador)],
        )

        result = trabajo_fijo.action_verificar_y_confirmar()

        self.assertTrue(result)
        self.assertTrue(trabajo_fijo.confirmado)
        asignaciones = self.env['portalgestor.asignacion'].browse(
            trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id').ids
        )
        self.assertTrue(all(asignaciones.mapped('confirmado')))

    def test_fixed_assignment_verification_confirms_midnight_range(self):
        trabajador = self._create_worker('Fijo Medianoche')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fields.Date.to_date('2099-05-20'),
            fields.Date.to_date('2099-05-22'),
            [(0.0, 1.0, trabajador)],
        )

        result = trabajo_fijo.action_verificar_y_confirmar()

        self.assertTrue(result)
        self.assertTrue(trabajo_fijo.confirmado)
        self.assertEqual(trabajo_fijo.total_dias_generados, 3)
        self.assertEqual(trabajo_fijo.total_lineas_generadas, 3)
        self.assertTrue(all(
            self.env['portalgestor.asignacion'].browse(
                trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id').ids
            ).mapped('confirmado')
        ))

    def test_fixed_assignment_verification_detects_overlapping_assignments(self):
        fecha = fields.Date.to_date('2099-05-22')
        trabajador = self._create_worker('Fijo Verificar Solape')
        self._create_assignment(
            self.usuario_b,
            fecha,
            [(9.0, 11.0, trabajador)],
        )
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [(10.0, 12.0, trabajador)],
        )

        action = trabajo_fijo.action_verificar_y_confirmar()

        self.assertEqual(action['res_model'], 'portalgestor.conflict.wizard')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.asignacion_mensual_id, trabajo_fijo)
        self.assertEqual(wizard.conflict_type, 'overlapping_batch')
        self.assertEqual(len(wizard.batch_conflict_line_ids), 1)

    def test_fixed_assignment_verification_batches_same_user_overwrites(self):
        fecha_inicio = fields.Date.to_date('2099-05-24')
        fecha_fin = fields.Date.to_date('2099-05-26')
        trabajador = self._create_worker('Fijo Batch Mismo Usuario')

        trabajo_fijo_original = self._create_fixed_assignment(
            self.usuario_a,
            fecha_inicio,
            fecha_fin,
            [(0.0, 1.0, trabajador)],
        )
        trabajo_fijo_original.action_verificar_y_confirmar()

        trabajo_fijo_nuevo = self._create_fixed_assignment(
            self.usuario_a,
            fecha_inicio,
            fecha_fin,
            [(0.0, 1.0, trabajador)],
        )

        action = trabajo_fijo_nuevo.action_verificar_y_confirmar()

        self.assertEqual(action['res_model'], 'portalgestor.conflict.wizard')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.conflict_type, 'overlapping_batch')
        self.assertEqual(len(wizard.batch_conflict_line_ids), 3)

        result = wizard.action_confirm()

        self.assertEqual(result['type'], 'ir.actions.act_window_close')
        self.assertTrue(trabajo_fijo_nuevo.confirmado)
        self.assertTrue(all(
            self.env['portalgestor.asignacion'].browse(
                trabajo_fijo_nuevo.asignacion_linea_ids.mapped('asignacion_id').ids
            ).mapped('confirmado')
        ))

    def test_fixed_assignment_verification_keeps_same_day_warning(self):
        fecha = fields.Date.to_date('2099-05-23')
        trabajador = self._create_worker('Fijo Verificar Aviso')
        self._create_assignment(
            self.usuario_b,
            fecha,
            [(8.0, 10.0, trabajador)],
        )
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [(10.0, 12.0, trabajador)],
        )

        action = trabajo_fijo.action_verificar_y_confirmar()

        self.assertEqual(action['res_model'], 'portalgestor.conflict.wizard')
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertEqual(wizard.asignacion_mensual_id, trabajo_fijo)
        self.assertEqual(wizard.conflict_type, 'info_same_day')
        self.assertIn(self.usuario_b.name, wizard.info_resumen)

        result = wizard.action_confirm()

        self.assertEqual(result['type'], 'ir.actions.act_window_close')
        self.assertTrue(trabajo_fijo.confirmado)
        self.assertTrue(all(
            self.env['portalgestor.asignacion'].browse(
                trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id').ids
            ).mapped('confirmado')
        ))

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

    def test_fixed_assignment_manual_day_override_survives_later_fixed_sync(self):
        trabajador_original = self._create_worker('Fijo Override Original')
        trabajador_nuevo = self._create_worker('Fijo Override Nuevo')
        fecha_inicio = fields.Date.to_date('2099-06-10')
        fecha_override = fields.Date.to_date('2099-06-12')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha_inicio,
            fecha_override,
            [(8.0, 10.0, trabajador_original)],
        )

        asignacion_override = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha_override),
        ])
        linea_generada = asignacion_override.lineas_ids
        linea_generada.write({'trabajador_id': trabajador_nuevo.id})

        excepcion = self.env['portalgestor.asignacion.mensual.excepcion'].search([
            ('asignacion_mensual_id', '=', trabajo_fijo.id),
            ('fecha', '=', fecha_override),
        ])
        self.assertEqual(excepcion.tipo, 'manual')
        self.assertFalse(linea_generada.asignacion_mensual_id)
        self.assertFalse(linea_generada.asignacion_mensual_linea_id)
        self.assertEqual(linea_generada.trabajador_id, trabajador_nuevo)

        trabajo_fijo.write({
            'fecha_fin': fields.Date.to_date('2099-06-13'),
        })

        asignacion_override = self.env['portalgestor.asignacion'].browse(asignacion_override.id)
        lineas_override = asignacion_override.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
        self.assertEqual(len(lineas_override), 1)
        self.assertEqual(lineas_override.trabajador_id, trabajador_nuevo)
        self.assertFalse(lineas_override.asignacion_mensual_id)

        asignacion_nueva = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fields.Date.to_date('2099-06-13')),
        ])
        self.assertEqual(asignacion_nueva.lineas_ids.trabajador_id, trabajador_original)
        self.assertEqual(asignacion_nueva.lineas_ids.asignacion_mensual_id, trabajo_fijo)

    def test_fixed_assignment_worker_change_via_assignment_write_survives_fixed_unlink(self):
        trabajador_1 = self._create_worker('Fijo Form 1')
        trabajador_2 = self._create_worker('Fijo Form 2')
        trabajador_3 = self._create_worker('Fijo Form 3')
        fecha = fields.Date.to_date('2099-06-18')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [
                (8.0, 10.0, trabajador_1),
                (10.0, 12.0, trabajador_2),
            ],
        )

        asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha),
        ])
        linea_a_cambiar = asignacion.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))[0]
        asignacion.write({
            'lineas_ids': [
                (1, linea_a_cambiar.id, {'trabajador_id': trabajador_3.id}),
            ],
        })

        trabajo_fijo = self.env['portalgestor.asignacion.mensual'].browse(trabajo_fijo.id)
        self.assertFalse(trabajo_fijo.asignacion_linea_ids.filtered(lambda linea: linea.fecha == fecha))

        trabajo_fijo.unlink()

        asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha),
        ])
        self.assertTrue(asignacion.exists())
        self.assertEqual(
            sorted(asignacion.lineas_ids.mapped('trabajador_id').ids),
            sorted([trabajador_2.id, trabajador_3.id]),
        )
        self.assertFalse(asignacion.lineas_ids.filtered('asignacion_mensual_id'))

    def test_fixed_assignment_extra_worker_makes_day_independent(self):
        trabajador = self._create_worker('Fijo Base')
        trabajador_extra = self._create_worker('Fijo Extra')
        fecha = fields.Date.to_date('2099-06-20')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [(9.0, 11.0, trabajador)],
        )

        asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha),
        ])
        self.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': asignacion.id,
            'hora_inicio': 12.0,
            'hora_fin': 14.0,
            'trabajador_id': trabajador_extra.id,
        })

        trabajo_fijo.write({
            'fecha_fin': fields.Date.to_date('2099-06-21'),
        })

        asignacion = self.env['portalgestor.asignacion'].browse(asignacion.id)
        self.assertEqual(
            sorted(asignacion.lineas_ids.mapped('trabajador_id').ids),
            sorted([trabajador.id, trabajador_extra.id]),
        )
        self.assertFalse(asignacion.lineas_ids.filtered('asignacion_mensual_id'))
        nueva_asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fields.Date.to_date('2099-06-21')),
        ])
        self.assertEqual(nueva_asignacion.lineas_ids.trabajador_id, trabajador)

    def test_independent_day_worker_removal_deletes_line(self):
        trabajador_1 = self._create_worker('Fijo Remove 1')
        trabajador_2 = self._create_worker('Fijo Remove 2')
        trabajador_3 = self._create_worker('Fijo Remove 3')
        fecha = fields.Date.to_date('2099-06-23')
        self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [
                (8.0, 10.0, trabajador_1),
                (10.0, 12.0, trabajador_2),
            ],
        )

        asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha),
        ])
        self.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': asignacion.id,
            'hora_inicio': 12.0,
            'hora_fin': 14.0,
            'trabajador_id': trabajador_3.id,
        })
        linea_borrar = asignacion.lineas_ids.filtered(lambda linea: linea.trabajador_id == trabajador_2)
        asignacion.write({
            'lineas_ids': [(2, linea_borrar.id, 0)],
        })

        asignacion = self.env['portalgestor.asignacion'].browse(asignacion.id)
        self.assertEqual(
            sorted(asignacion.lineas_ids.mapped('trabajador_id').ids),
            sorted([trabajador_1.id, trabajador_3.id]),
        )
        self.assertFalse(asignacion.lineas_ids.filtered('asignacion_mensual_id'))

    def test_fixed_assignment_direct_line_unlink_makes_day_independent(self):
        trabajador_1 = self._create_worker('Fijo Direct Unlink 1')
        trabajador_2 = self._create_worker('Fijo Direct Unlink 2')
        fecha = fields.Date.to_date('2099-06-24')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [
                (8.0, 10.0, trabajador_1),
                (10.0, 12.0, trabajador_2),
            ],
        )

        asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha),
        ])
        linea_borrar = asignacion.lineas_ids.filtered(lambda linea: linea.trabajador_id == trabajador_2)

        linea_borrar.unlink()

        trabajo_fijo = self.env['portalgestor.asignacion.mensual'].browse(trabajo_fijo.id)
        self.assertFalse(trabajo_fijo.asignacion_linea_ids.filtered(lambda linea: linea.fecha == fecha))
        excepcion = self.env['portalgestor.asignacion.mensual.excepcion'].search([
            ('asignacion_mensual_id', '=', trabajo_fijo.id),
            ('fecha', '=', fecha),
        ])
        self.assertEqual(excepcion.tipo, 'manual')

        asignacion = self.env['portalgestor.asignacion'].browse(asignacion.id)
        self.assertEqual(asignacion.lineas_ids.trabajador_id, trabajador_1)
        self.assertFalse(asignacion.lineas_ids.asignacion_mensual_id)

        trabajo_fijo.unlink()

        asignacion = self.env['portalgestor.asignacion'].browse(asignacion.id)
        self.assertTrue(asignacion.exists())
        self.assertEqual(asignacion.lineas_ids.trabajador_id, trabajador_1)
        self.assertFalse(asignacion.lineas_ids.asignacion_mensual_id)

    def test_fixed_assignment_hour_change_keeps_day_linked_to_fixed(self):
        trabajador = self._create_worker('Fijo Horas')
        fecha = fields.Date.to_date('2099-06-25')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [(9.0, 11.0, trabajador)],
        )

        asignacion = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', fecha),
        ])
        asignacion.lineas_ids.write({
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
        })
        self.assertEqual(asignacion.lineas_ids.asignacion_mensual_id, trabajo_fijo)

        trabajo_fijo.unlink()

        self.assertFalse(
            self.env['portalgestor.asignacion'].search([
                ('usuario_id', '=', self.usuario_a.id),
                ('fecha', '=', fecha),
            ])
        )

    def test_worker_baja_releases_fixed_assignments_from_today_forward_only(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        ayer = hoy - timedelta(days=1)
        manana = hoy + timedelta(days=1)
        trabajador = self._create_worker('Fijo Baja')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            ayer,
            manana,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_pasada = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', ayer),
        ])
        asignacion_hoy = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', hoy),
        ])
        asignacion_futura = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', manana),
        ])

        trabajador.with_context(
            portalgestor_cutoff_datetime=datetime.combine(hoy, datetime.min.time()),
        ).write({'baja': True})

        self.assertEqual(asignacion_pasada.lineas_ids.trabajador_id, trabajador)
        self.assertEqual(asignacion_pasada.lineas_ids.asignacion_mensual_id, trabajo_fijo)
        self.assertFalse(asignacion_hoy.lineas_ids.trabajador_id)
        self.assertFalse(asignacion_hoy.lineas_ids.asignacion_mensual_id)
        self.assertEqual(asignacion_hoy.calendar_bucket_type, 'pending')
        self.assertFalse(asignacion_futura.lineas_ids.trabajador_id)
        self.assertFalse(asignacion_futura.lineas_ids.asignacion_mensual_id)
        self.assertEqual(asignacion_futura.calendar_bucket_type, 'pending')

        trabajo_fijo.write({
            'fecha_fin': hoy + timedelta(days=2),
        })

        self.assertFalse(
            self.env['portalgestor.asignacion'].search([
                ('usuario_id', '=', self.usuario_a.id),
                ('fecha', '=', hoy + timedelta(days=2)),
            ])
        )

    def test_user_baja_cancels_fixed_assignments_from_today_forward_only(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        ayer = hoy - timedelta(days=1)
        manana = hoy + timedelta(days=1)
        trabajador = self._create_worker('Usuario Baja Fijo')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            ayer,
            manana,
            [(8.0, 10.0, trabajador)],
        )
        asignacion_pasada = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', ayer),
        ])
        asignacion_hoy = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', hoy),
        ])
        asignacion_futura = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario_a.id),
            ('fecha', '=', manana),
        ])

        self.usuario_a.with_context(
            portalgestor_cutoff_datetime=datetime.combine(hoy, datetime.min.time()),
        ).write({'baja': True})

        self.assertTrue(asignacion_pasada.exists())
        self.assertFalse(asignacion_hoy.exists())
        self.assertFalse(asignacion_futura.exists())

        trabajo_fijo.write({
            'fecha_fin': hoy + timedelta(days=2),
        })

        self.assertFalse(
            self.env['portalgestor.asignacion'].search([
                ('usuario_id', '=', self.usuario_a.id),
                ('fecha', '=', hoy + timedelta(days=2)),
            ])
        )

    def test_worker_baja_only_clears_future_hours_for_today(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        manana = hoy + timedelta(days=1)
        trabajador_baja = self._create_worker('Baja Horas Trabajador')
        trabajador_soporte = self._create_worker('Baja Horas Soporte')

        asignacion_hoy = self._create_assignment(
            self.usuario_a,
            hoy,
            [
                (8.0, 12.0, trabajador_baja),
                (12.0, 15.0, trabajador_baja),
                (15.0, 17.0, trabajador_soporte),
            ],
        )
        asignacion_manana = self._create_assignment(
            self.usuario_a,
            manana,
            [(8.0, 10.0, trabajador_baja)],
        )

        trabajador_baja.with_context(
            portalgestor_cutoff_datetime=datetime.combine(hoy, datetime.min.time()).replace(hour=12, minute=30),
        ).write({'baja': True})

        asignacion_hoy = self.env['portalgestor.asignacion'].browse(asignacion_hoy.id)
        horas_hoy = sorted(
            (
                linea.hora_inicio,
                linea.hora_fin,
                linea.trabajador_id.id or False,
            )
            for linea in asignacion_hoy.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
        )
        self.assertEqual(
            horas_hoy,
            [
                (8.0, 12.0, trabajador_baja.id),
                (12.0, 12.5, trabajador_baja.id),
                (12.5, 15.0, False),
                (15.0, 17.0, trabajador_soporte.id),
            ],
        )
        self.assertFalse(self.env['portalgestor.asignacion'].browse(asignacion_manana.id).lineas_ids.trabajador_id)

    def test_user_baja_only_clears_future_hours_for_today(self):
        hoy = fields.Date.to_date(fields.Date.context_today(self.env['portalgestor.asignacion']))
        manana = hoy + timedelta(days=1)
        trabajador = self._create_worker('Baja Horas Usuario')

        asignacion_hoy = self._create_assignment(
            self.usuario_a,
            hoy,
            [
                (8.0, 12.0, trabajador),
                (12.0, 15.0, trabajador),
            ],
        )
        asignacion_manana = self._create_assignment(
            self.usuario_a,
            manana,
            [(8.0, 10.0, trabajador)],
        )

        self.usuario_a.with_context(
            portalgestor_cutoff_datetime=datetime.combine(hoy, datetime.min.time()).replace(hour=12, minute=30),
        ).write({'baja': True})

        asignacion_hoy = self.env['portalgestor.asignacion'].browse(asignacion_hoy.id)
        self.assertTrue(asignacion_hoy.exists())
        self.assertEqual(
            sorted(
                (
                    linea.hora_inicio,
                    linea.hora_fin,
                    linea.trabajador_id.id,
                )
                for linea in asignacion_hoy.lineas_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.id))
            ),
            [(8.0, 12.0, trabajador.id), (12.0, 12.5, trabajador.id)],
        )
        self.assertFalse(self.env['portalgestor.asignacion'].browse(asignacion_manana.id).exists())

    def test_assignment_verification_rechecks_worker_vacations_after_date_change(self):
        fecha_libre = fields.Date.to_date('2099-08-10')
        fecha_vacacion = fields.Date.to_date('2099-08-11')
        trabajador = self._create_worker('Cambio Fecha Vacacion')

        self.env['trabajadores.vacacion'].create({
            'trabajador_id': trabajador.id,
            'date_start': fecha_vacacion,
            'date_stop': fecha_vacacion,
        })

        asignacion = self._create_assignment(
            self.usuario_a,
            fecha_libre,
            [(8.0, 10.0, trabajador)],
        )
        asignacion.write({'fecha': fecha_vacacion})

        with self.assertRaises(ValidationError):
            asignacion.action_verificar_y_confirmar()

    def test_fixed_assignment_verification_rechecks_worker_vacations(self):
        fecha = fields.Date.to_date('2099-08-12')
        trabajador = self._create_worker('Fijo Vacacion Verificar')

        self.env['trabajadores.vacacion'].create({
            'trabajador_id': trabajador.id,
            'date_start': fecha,
            'date_stop': fecha,
        })

        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha,
            fecha,
            [(8.0, 10.0, trabajador)],
        )

        with self.assertRaises(ValidationError):
            trabajo_fijo.action_verificar_y_confirmar()

    def test_worker_search_excludes_vacations_from_fixed_range_context(self):
        fecha_inicio = fields.Date.to_date('2099-07-01')
        fecha_fin = fields.Date.to_date('2099-07-05')
        trabajador_en_vacaciones = self._create_worker('Fijo Vacaciones')
        trabajador_disponible = self._create_worker('Fijo Disponible')

        self.env['trabajadores.vacacion'].create({
            'trabajador_id': trabajador_en_vacaciones.id,
            'date_start': fields.Date.to_date('2099-07-03'),
            'date_stop': fields.Date.to_date('2099-07-04'),
        })

        trabajadores = self.env['trabajadores.trabajador'].with_context(
            exclude_vacaciones_fecha_inicio=fields.Date.to_string(fecha_inicio),
            exclude_vacaciones_fecha_fin=fields.Date.to_string(fecha_fin),
        ).search(
            [('id', 'in', [trabajador_en_vacaciones.id, trabajador_disponible.id])],
            order='id',
        )

        self.assertEqual(trabajadores.ids, [trabajador_disponible.id])
        form_arch = self.env.ref('portalGestor.portalgestor_asignacion_mensual_form').arch_db
        self.assertIn('exclude_vacaciones_fecha_inicio', form_arch)
        self.assertIn("('baja', '=', False)", form_arch)

    def test_assignment_forms_include_delete_button(self):
        asignacion_form_arch = self.env.ref('portalGestor.portalgestor_asignacion_form').arch_db
        asignacion_mensual_form_arch = self.env.ref('portalGestor.portalgestor_asignacion_mensual_form').arch_db

        self.assertIn('action_eliminar_horario', asignacion_form_arch)
        self.assertIn('action_eliminar_horario', asignacion_mensual_form_arch)

    def test_confirmed_assignment_restore_snapshot_when_edit_is_discarded(self):
        fecha_confirmada = fields.Date.to_date('2099-08-20')
        fecha_editada = fields.Date.to_date('2099-08-21')
        trabajador = self._create_worker('Snapshot Diario')
        asignacion = self._create_assignment(
            self.usuario_a,
            fecha_confirmada,
            [(8.0, 10.0, trabajador)],
        )
        asignacion.write({'confirmado': True})

        asignacion.action_editar()
        asignacion.write({
            'fecha': fecha_editada,
            'lineas_ids': [(1, asignacion.lineas_ids.id, {'hora_inicio': 9.0, 'hora_fin': 11.0})],
        })
        asignacion.action_descartar_edicion()
        asignacion.invalidate_recordset(['fecha', 'confirmado', 'edit_session_pending', 'edit_snapshot_data', 'lineas_ids'])

        self.assertTrue(asignacion.confirmado)
        self.assertFalse(asignacion.edit_session_pending)
        self.assertFalse(asignacion.edit_snapshot_data)
        self.assertEqual(asignacion.fecha, fecha_confirmada)
        self.assertEqual(asignacion.lineas_ids.hora_inicio, 8.0)
        self.assertEqual(asignacion.lineas_ids.hora_fin, 10.0)
        self.assertEqual(asignacion.lineas_ids.trabajador_id, trabajador)

    def test_confirmed_fixed_assignment_restore_snapshot_when_edit_is_discarded(self):
        fecha_inicio = fields.Date.to_date('2099-08-22')
        fecha_fin = fields.Date.to_date('2099-08-24')
        trabajador_1 = self._create_worker('Snapshot Fijo 1')
        trabajador_2 = self._create_worker('Snapshot Fijo 2')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_a,
            fecha_inicio,
            fecha_fin,
            [(8.0, 10.0, trabajador_1)],
        )
        trabajo_fijo.write({'confirmado': True})
        trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id').write({'confirmado': True})

        trabajo_fijo.action_editar()
        trabajo_fijo.write({
            'linea_fija_ids': [(1, trabajo_fijo.linea_fija_ids.id, {'trabajador_id': trabajador_2.id})],
        })
        trabajo_fijo.action_descartar_edicion()
        trabajo_fijo.invalidate_recordset(['confirmado', 'edit_session_pending', 'edit_snapshot_data', 'linea_fija_ids'])

        self.assertTrue(trabajo_fijo.confirmado)
        self.assertFalse(trabajo_fijo.edit_session_pending)
        self.assertFalse(trabajo_fijo.edit_snapshot_data)
        self.assertEqual(trabajo_fijo.linea_fija_ids.trabajador_id, trabajador_1)
        self.assertTrue(all(trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id.confirmado')))

    def test_vacation_calendar_uses_worker_internal_color(self):
        trabajador = self._create_worker('Color Vacaciones')
        trabajador.write({'color': 4})
        vacacion = self.env['trabajadores.vacacion'].create({
            'trabajador_id': trabajador.id,
            'date_start': fields.Date.to_date('2099-08-25'),
            'date_stop': fields.Date.to_date('2099-08-25'),
        })

        calendar_arch = self.env.ref('trabajadores.vacacion_calendar').arch_db

        self.assertEqual(vacacion.trabajador_color, 4)
        self.assertIn('color="trabajador_color"', calendar_arch)

    def test_assignment_rejects_usuario_without_ap_service(self):
        usuario_sin_ap = self.env['usuarios.usuario'].create({
            'name': 'Usuario sin AP',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
        })
        trabajador = self._create_worker('Sin AP')

        with self.assertRaises(ValidationError):
            self._create_assignment(
                usuario_sin_ap,
                fields.Date.to_date('2026-03-28'),
                [(8.0, 10.0, trabajador)],
            )

    def test_fixed_assignment_rejects_usuario_without_ap_service(self):
        usuario_sin_ap = self.env['usuarios.usuario'].create({
            'name': 'Usuario fijo sin AP',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
        })
        trabajador = self._create_worker('Fijo sin AP')

        with self.assertRaises(ValidationError):
            self._create_fixed_assignment(
                usuario_sin_ap,
                fields.Date.to_date('2026-03-01'),
                fields.Date.to_date('2026-03-31'),
                [(8.0, 10.0, trabajador)],
            )

    def test_usuario_report_wizard_payload_contains_services_and_total(self):
        fecha = fields.Date.to_date('2026-03-29')
        trabajador = self._create_worker('Reporte Usuario')
        usuario = self.env['usuarios.usuario'].create({
            'name': 'Lucia',
            'apellido1': 'Perez',
            'apellido2': 'Santos',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
            'servicio_ids': [(6, 0, [self.ap_service.id])],
        })

        self._create_assignment(
            usuario,
            fecha,
            [
                (8.0, 10.5, trabajador),
                (11.0, 13.0, trabajador),
            ],
        )

        wizard = self.env['portalgestor.usuario.report.wizard'].create({
            'usuario_ids': [(6, 0, [usuario.id])],
            'mes': '3',
            'anio': '2026',
        })
        payload = wizard._get_report_payload_for_user(usuario)

        self.assertEqual(payload['usuario_full_name'], 'Lucia Perez Santos')
        self.assertEqual(payload['services_label'], 'AP')
        self.assertEqual(payload['total_duration_label'], '4 Horas y 30 minutos')
        self.assertEqual(len(payload['lines']), 2)
        self.assertEqual(payload['lines'][0]['duration_label'], '2 Horas y 30 minutos')

    def test_usuario_report_wizard_exports_zip_for_multiple_csv_users(self):
        trabajador = self._create_worker('Reporte CSV ZIP')
        fecha = fields.Date.to_date('2026-03-30')

        self._create_assignment(self.usuario_a, fecha, [(8.0, 10.0, trabajador)])
        self._create_assignment(self.usuario_b, fecha, [(10.0, 12.0, trabajador)])

        wizard = self.env['portalgestor.usuario.report.wizard'].create({
            'usuario_ids': [(6, 0, [self.usuario_a.id, self.usuario_b.id])],
            'mes': '3',
            'anio': '2026',
            'formato_salida': 'csv',
        })
        action = wizard.action_generate_report()

        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('download_file', action['url'])
        self.assertTrue(wizard.download_file)
        self.assertTrue(wizard.download_filename.endswith('.zip'))
