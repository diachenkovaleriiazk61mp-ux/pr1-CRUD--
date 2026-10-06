"""Stateless vaccination CRUD API. All persistent state lives in PostgreSQL."""
import os
import socket
from datetime import date
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException

FIELDS = ('patient_code', 'vaccine', 'batch', 'dose_number', 'administration_date', 'facility')

def validate(data):
    errors = {}
    if not isinstance(data, dict):
        return {'body': 'Очікується JSON об’єкт'}
    for key in data.keys() - set(FIELDS):
        errors[key] = 'Невідоме поле; id генерує база'
    for key in FIELDS:
        if key not in data:
            errors[key] = 'Обов’язкове поле'
    for key in ('patient_code', 'vaccine', 'batch', 'facility'):
        if key in data and (not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 200):
            errors[key] = 'Непорожній рядок до 200 символів'
    if 'dose_number' in data and (type(data['dose_number']) is not int or not 1 <= data['dose_number'] <= 4):
        errors['dose_number'] = 'Ціле число від 1 до 4'
    if 'administration_date' in data:
        try:
            value = data['administration_date']
            if not isinstance(value, str) or len(value) != 10:
                raise ValueError()
            parsed = date.fromisoformat(value)
            if parsed > date.today():
                errors['administration_date'] = 'Дата введення не може бути в майбутньому'
        except (TypeError, ValueError):
            errors['administration_date'] = 'Дата у форматі YYYY-MM-DD'
    return errors

def create_app(pool=None):
    if pool is None:
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row
        pool = ConnectionPool(os.environ['DATABASE_URL'], min_size=1, max_size=16,
                              kwargs={'row_factory': dict_row}, timeout=3, open=True)
        pool.wait(timeout=60)
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 16384

    def normalize(row):
        return {k: v.isoformat() if isinstance(v, date) else v for k, v in row.items()}

    @app.after_request
    def instance(response):
        response.headers['X-Instance-ID'] = socket.gethostname()
        return response

    @app.errorhandler(Exception)
    def failure(exc):
        if isinstance(exc, HTTPException):
            code = 400 if exc.code in (400, 413, 415) else exc.code
            return jsonify(errors={'body': exc.description}), code
        app.logger.exception('Request failed')
        return jsonify(errors={'database': 'Сервіс тимчасово недоступний'}), 503

    @app.get('/healthz')
    def health():
        try:
            with pool.connection() as conn:
                conn.execute('SELECT 1').fetchone()
            return jsonify(status='ready')
        except Exception:
            return jsonify(status='not_ready'), 503

    @app.route('/vaccinations', methods=['POST', 'GET'])
    def collection():
        if request.method == 'POST':
            data = request.get_json()
            errors = validate(data)
            if errors:
                return jsonify(errors=errors), 400
            with pool.connection() as conn:
                row = conn.execute('INSERT INTO vaccinations (' + ','.join(FIELDS) + ') VALUES (' + ','.join(['%s']*6) + ') RETURNING *', tuple(data[k] for k in FIELDS)).fetchone()
            return jsonify(normalize(row)), 201
        errors = {}
        for key, default, lo, hi in [('limit', '20', 1, 100), ('offset', '0', 0, 2147483647)]:
            try:
                value = int(request.args.get(key, default))
                if not lo <= value <= hi:
                    raise ValueError()
            except ValueError:
                errors[key] = f'Ціле число від {lo} до {hi}'
        if errors:
            return jsonify(errors=errors), 400
        limit, offset = int(request.args.get('limit', 20)), int(request.args.get('offset', 0))
        vaccine = request.args.get('vaccine')
        clause, args = (' WHERE vaccine = %s', (vaccine,)) if vaccine is not None else ('', ())
        with pool.connection() as conn:
            # Count and page share one snapshot even with concurrent writers.
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            total = conn.execute('SELECT count(*) AS total FROM vaccinations' + clause, args).fetchone()['total']
            rows = conn.execute('SELECT * FROM vaccinations' + clause + ' ORDER BY id LIMIT %s OFFSET %s', args + (limit, offset)).fetchall()
        return jsonify(items=[normalize(r) for r in rows], total=total, limit=limit, offset=offset)

    @app.route('/vaccinations/<int:record_id>', methods=['GET', 'PUT', 'DELETE'])
    def record(record_id):
        if request.method == 'PUT':
            data = request.get_json()
            errors = validate(data)
            if errors:
                return jsonify(errors=errors), 400
        with pool.connection() as conn:
            if request.method == 'GET':
                row = conn.execute('SELECT * FROM vaccinations WHERE id=%s', (record_id,)).fetchone()
            elif request.method == 'PUT':
                row = conn.execute('UPDATE vaccinations SET ' + ','.join(k+'=%s' for k in FIELDS) + ' WHERE id=%s RETURNING *', tuple(data[k] for k in FIELDS)+(record_id,)).fetchone()
            else:
                row = conn.execute('DELETE FROM vaccinations WHERE id=%s RETURNING id', (record_id,)).fetchone()
        if row is None:
            return jsonify(errors={'id': 'Запис не знайдено'}), 404
        return ('', 204) if request.method == 'DELETE' else jsonify(normalize(row))
    return app
