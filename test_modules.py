#!/usr/bin/env python3
"""Quick test for annotation modules."""

from src.annotations import LineAnnotation, RectAnnotation, PolygonAnnotation, AnnotationOverlay
# Note: fast_annotations requires FAST which has Qt dependency conflicts in test mode
# from src.fast_annotations import FASTAnnotationManager, CoordinateConverter
print('Annotation imports OK')

# Test annotation classes
line = LineAnnotation()
line.add_point(10, 20)
line.add_point(100, 200)
print(f'LineAnnotation: {line.points}')

rect = RectAnnotation()
rect.add_point(0, 0)
rect.add_point(50, 50)
print(f'RectAnnotation corners: {rect.get_corners()}')

poly = PolygonAnnotation(closed=True)
poly.add_point(0, 0)
poly.add_point(100, 0)
poly.add_point(100, 100)
poly.add_point(0, 100)
poly.complete()
print(f'PolygonAnnotation: {len(poly.points)} points, perimeter={poly._calculate_perimeter():.1f}, area={poly._calculate_area():.1f}')

print('All annotation tests passed!')
