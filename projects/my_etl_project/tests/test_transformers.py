import unittest
import pandas as pd
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils import format_plat_nomor
from src.transformers import round_odo

class TestUtils(unittest.TestCase):

    def test_format_plat_nomor(self):
        """Test format_plat_nomor function"""
        # Test valid plates
        self.assertEqual(format_plat_nomor('b1234abc'), 'B 1234 ABC')
        self.assertEqual(format_plat_nomor(' B 1234 ABC '), 'B 1234 ABC')
        self.assertEqual(format_plat_nomor('D5678EFG'), 'D 5678 EFG')
        self.assertEqual(format_plat_nomor('B1111'), 'B 1111')
        
        # Test edge cases
        self.assertIsNone(format_plat_nomor(''))
        self.assertIsNone(format_plat_nomor(None))
        self.assertIsNone(format_plat_nomor(12345))

class TestTransformers(unittest.TestCase):

    def test_round_odo(self):
        """Test round_odo function with asset list"""
        # Create mock asset list
        asset_list = pd.DataFrame({
            'Plat Nomor': ['B 1234 ABC', 'D 5678 EFG', 'C 1111 ZZZ'],
            'Umur Kendaraan': [12, 24, 12]
        })
        
        # Test row with Umur <= 12 (5-digit rounding)
        # Input: 123456, digit ke-6 = 6 (>= 5), round up: 12345 + 1 = 12346
        row1 = pd.Series({
            'vehicle_license_plate': 'B 1234 ABC',
            'odometer': 123456
        })
        result1 = round_odo(row1, asset_list)
        self.assertEqual(result1, 12346)  # Rounded up because 6th digit >= 5
        
        # Test row with Umur <= 12, no rounding needed (6th digit < 5)
        row1b = pd.Series({
            'vehicle_license_plate': 'C 1111 ZZZ',
            'odometer': 123454
        })
        result1b = round_odo(row1b, asset_list)
        self.assertEqual(result1b, 12345)  # No rounding because 6th digit < 5
        
        # Test row with Umur == 24 (6-digit rounding)
        # Input: 1234567, digit ke-7 = 7 (>= 5), round up: 123456 + 1 = 123457
        row2 = pd.Series({
            'vehicle_license_plate': 'D 5678 EFG',
            'odometer': 1234567
        })
        result2 = round_odo(row2, asset_list)
        self.assertEqual(result2, 123457)  # Rounded up because 7th digit >= 5
        
        # Test row without matching asset (no rounding)
        row3 = pd.Series({
            'vehicle_license_plate': 'Z 9999 XYZ',
            'odometer': 123456
        })
        result3 = round_odo(row3, asset_list)
        self.assertEqual(result3, 123456)  # No change

if __name__ == '__main__':
    unittest.main()
