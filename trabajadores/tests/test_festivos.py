# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestTrabajadoresFestivos(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Festivos',
            'code': 'ZONA_FESTIVOS',
        })
        cls.localidad_a = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Festivos A',
        })
        cls.localidad_b = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Festivos B',
        })

    @classmethod
    def _create_worker(cls, suffix):
        return cls.env['trabajadores.trabajador'].create({
            'name': f'AP {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    def test_action_sync_year_uses_boe_fallback_when_csv_has_no_target_year(self):
        csv_text = (
            "Fichero actualizado a fecha: 2024-01-01 00:00:00;;;\n"
            "Nombre de la fiesta;Fecha festivo;Trasladado;Fecha disfrute\n"
            "Año Nuevo;01/01/2024;No;01/01/2024\n"
        )
        boe_search_html = '<a href="../buscar/doc.php?id=BOE-A-2025-21667">Más...</a>'
        boe_doc_html = """
            <table>
              <tbody>
                <tr>
                  <td id="header2304B" class="cuerpo_tabla_izq" axis="fecha">23 Fiesta de Castilla y León.</td>
                  <td class="cuerpo_tabla_centro" headers="headerAbril header2304B headerCastillaYL">
                    <abbr title="Fiesta de Comunidad Autónoma">***</abbr>
                  </td>
                </tr>
              </tbody>
            </table>
        """

        holiday_model = self.env['trabajadores.festivo.oficial']
        with patch.object(type(holiday_model), '_fetch_jcyl_csv_text', return_value=csv_text), patch.object(
            type(holiday_model), '_fetch_boe_search_html', return_value=boe_search_html
        ), patch.object(type(holiday_model), '_fetch_boe_doc_html', return_value=boe_doc_html):
            holiday_model.action_sync_year(2026)

        holiday = holiday_model.search([('fecha', '=', fields.Date.to_date('2026-04-23'))], limit=1)
        self.assertTrue(holiday)
        self.assertEqual(holiday.source_kind, 'boe_html')
        self.assertEqual(holiday.source_scope, 'autonomic')
        self.assertEqual(holiday.name, 'Fiesta de Castilla y León')

    def test_sync_does_not_override_manual_corrections(self):
        holiday_date = fields.Date.to_date('2026-04-23')
        holiday = self.env['trabajadores.festivo.oficial'].search([('fecha', '=', holiday_date)], limit=1)
        if holiday:
            holiday.write({
                'name': 'Festivo manual',
                'source_scope': 'autonomic',
                'manual_override': True,
            })
        else:
            holiday = self.env['trabajadores.festivo.oficial'].create({
                'name': 'Festivo manual',
                'fecha': holiday_date,
                'source_scope': 'autonomic',
                'manual_override': True,
            })
        boe_search_html = '<a href="../buscar/doc.php?id=BOE-A-2025-21667">Más...</a>'
        boe_doc_html = """
            <table>
              <tbody>
                <tr>
                  <td id="header2304B" class="cuerpo_tabla_izq" axis="fecha">23 Fiesta de Castilla y León.</td>
                  <td class="cuerpo_tabla_centro" headers="headerAbril header2304B headerCastillaYL">
                    <abbr title="Fiesta de Comunidad Autónoma">***</abbr>
                  </td>
                </tr>
              </tbody>
            </table>
        """
        holiday_model = self.env['trabajadores.festivo.oficial']
        with patch.object(type(holiday_model), '_fetch_jcyl_csv_text', return_value='Nombre de la fiesta;Fecha festivo;Trasladado;Fecha disfrute\n'), patch.object(
            type(holiday_model), '_fetch_boe_search_html', return_value=boe_search_html
        ), patch.object(type(holiday_model), '_fetch_boe_doc_html', return_value=boe_doc_html):
            holiday_model.action_sync_year(2026)

        holiday.invalidate_recordset(['name', 'manual_override'])
        self.assertEqual(holiday.name, 'Festivo manual')
        self.assertTrue(holiday.manual_override)

    def test_local_holiday_rejects_duplicate_locality_date(self):
        date_value = fields.Date.to_date('2026-04-24')
        self.env['trabajadores.festivo.local'].create({
            'fecha': date_value,
            'localidad_id': self.localidad_a.id,
            'name': 'Sanidad local',
        })
        with self.assertRaises(ValidationError):
            self.env['trabajadores.festivo.local'].create({
                'fecha': date_value,
                'localidad_id': self.localidad_a.id,
                'name': 'Duplicado',
            })

    def test_local_holiday_allows_same_date_with_different_locality(self):
        date_value = fields.Date.to_date('2026-04-25')
        self.env['trabajadores.festivo.local'].create({
            'fecha': date_value,
            'localidad_id': self.localidad_a.id,
            'name': 'Fiesta A',
        })
        second_holiday = self.env['trabajadores.festivo.local'].create({
            'fecha': date_value,
            'localidad_id': self.localidad_b.id,
            'name': 'Fiesta B',
        })

        self.assertTrue(second_holiday)

    def test_worker_primary_festive_locality_is_migrated_to_multiple_localities(self):
        worker = self.env['trabajadores.trabajador'].create({
            'name': 'AP Localidad Unica',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [self.zone.id])],
            'festivo_localidad_id': self.localidad_a.id,
        })

        self.assertIn(self.localidad_a, worker.festivo_localidad_ids)

    def test_worker_action_open_festivos_locales_uses_all_selected_localities(self):
        worker = self.env['trabajadores.trabajador'].create({
            'name': 'AP Multi Localidad',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [self.zone.id])],
            'festivo_localidad_ids': [(6, 0, [self.localidad_a.id, self.localidad_b.id])],
        })

        action = worker.action_open_festivos_locales()
        self.assertEqual(action['domain'][0][0], 'localidad_id')
        self.assertEqual(action['domain'][0][1], 'in')
        self.assertEqual(set(action['domain'][0][2]), {self.localidad_a.id, self.localidad_b.id})
