#! /usr/bin/env python3
#-*- coding: utf-8 -*-

import sys, os, cgi, subprocess, psycopg2, re
import cgitb
root = "/data/project/polygons/polygons-generation"
sys.path.append(root)
from tools import utils

form      = cgi.FieldStorage()
rel_id    = int(form.getvalue("id", -1))
x         = float(form.getvalue("x", -1))
y         = float(form.getvalue("y", -1))
z         = float(form.getvalue("z", -1))
refresh   = form.getvalue("refresh") != None

show = utils.show
cgitb.enable()

PgConn    = utils.get_dbconn()
PgCursor  = PgConn.cursor()

def get_state_timestamp(name):
    f = open(name)
    for line in f:
        (key, sep, value) = line.partition("=")
        if key.strip() == "timestamp":
            return value.replace("\\", "")

    return ""


if rel_id == -1:
    utils.print_header("Polygon creation")
    show(u"<h1>%s</h1>" % ("Polygon creation"))
    show(u"<p>Database was last updated on: %s</p>" % get_state_timestamp("/data/work/osmbin/replication/state.txt"))
    show(u"<p>This will generate the whole geometry of the given OSM relation id, with the corresponding sub-relations. When the geometry is available, it is possible to generate simplified geometries from this one, and export them as .poly, GeoJSON, WKT or image formats.</p>")
    show(u"<form method='GET' action=''>")
    show(u"<label for='id'>%s</label>" % "Id of relation")
    show(u"<input type='text' name='id' id='id'>")
    show(u"<input type='submit'>")
    show(u"</form>")
    show(u"<br>\n")

    show(u"<h1>%s</h1>" % ("Import of an user polygon"))
    show(u"<p>Use this if you want to import your own .poly file, and do union operations with OSM relations.</p>")
    show(u"<form method='POST' action='import_poly.py' enctype='multipart/form-data'>")
    show(u"<label for='name'>%s</label>" % "Name")
    show(u"<input type='text' name='name' id='name'>")
    show(u"<label for='poly'>%s</label>" % ".poly file")
    show(u"<input type='file' name='poly' id='poly'>")
    show(u"<input type='submit'>")
    show(u"</form>")
    show(u"<br>\n")

    show(u"<h1>%s</h1>" % ("List of recently generated polygons"))

    show(u"<p>Here are the latest generated polygons with this application.</p>")

    show(u"<table class='sortable'>")
    show(u"  <tr>")
    show(u"    <th>%s</th>" % ("id"))
    show(u"    <th class='sorttable_sorted_reverse'>%s<span id='sorttable_sortrevind'>&nbsp;▴</span></th>" % ("timestamp"))
    show(u"    <th>%s</th>" % ("name"))
    show(u"    <th>%s</th>" % ("admin"))
    show(u"  </tr>")

    sql_list = """select polygons.id, timestamp, relations.tags
         from polygons
         LEFT JOIN relations ON relations.id = polygons.id
         WHERE params = '0'
         ORDER BY timestamp DESC
         LIMIT 20"""
    PgCursor.execute(sql_list)

    results = PgCursor.fetchall()

    for res in results:
        show(u"  <tr>")
        show(u"    <td><a href='?id=%d'>%d</a></td>" % (res["id"], res["id"]))
        show(u"    <td>" + str(res["timestamp"]) + "</td>")
        if res["tags"] is not None and "name" in res["tags"]:
            show(u"    <td>" + res["tags"]["name"] + "</td>")
        else:
            show(u"    <td></td>")
        if res["tags"] is not None and "admin_level" in res["tags"]:
            show(u"    <td>" + res["tags"]["admin_level"] + "</td>")
        else:
            show(u"    <td></td>")
        show(u"  </tr>")

    show(u"</table>")

    show(u"<h1>%s</h1>" % ("List of recently uploaded polygons"))

    show(u"<p>Here are the latest uploaded polygons with this application.</p>")

    show(u"<table class='sortable'>")
    show(u"  <tr>")
    show(u"    <th>%s</th>" % ("name"))
    show(u"    <th class='sorttable_sorted_reverse'>%s<span id='sorttable_sortrevind'>&nbsp;▴</span></th>" % ("timestamp"))
    show(u"  </tr>")

    sql_list = """select name, timestamp
         from polygons_user
         ORDER BY timestamp DESC
         LIMIT 20"""
    PgCursor.execute(sql_list)

    results = PgCursor.fetchall()

    for res in results:
        show(u"  <tr>")
        show(u"    <td><a href='show_polygon.py?name=%s'>%s</a></td>" % (res["name"], res["name"]))
        show(u"    <td>" + str(res["timestamp"]) + "</td>")
        show(u"  </tr>")

    show(u"</table>")


    sys.exit(0)

def parse_pg_notices(notices):
  re_lat_lon = re.compile("(.*point) ([-0-9.]*)f ([-0-9.]*)f - ways: (.*)$")
  s = u""
  for n in notices:
    line = n
    m = re_lat_lon.match(line)
    if m:
      lon = float(m.group(2))
      lat = float(m.group(3))
      ways = m.group(4).split(" ")
      ways = ["<a target='josm' href='http://127.0.0.1:8111/load_and_zoom?left=%f&right=%f&top=%f&bottom=%f&select=way%d'>%d</a>" % (lon-0.005, lon+0.005, lat+0.005, lat-0.005, int(i), int(i)) for i in ways]
      ways = " ".join(ways)
      params = (m.group(1), lon-0.0005, lon+0.0005, lat+0.0005, lat-0.0005, m.group(2) + "f " + m.group(3) + "f", ways)
      line = re_lat_lon.sub(line, "%s <a target='josm' href='http://127.0.0.1:8111/zoom?left=%f&right=%f&top=%f&bottom=%f'>%s</a> - ways: %s\n" % params)
    s += line

  s = s.replace("\n", "<br>\n")
  return s

if y > 0 and z > 0:
    sys.stdout.flush()
    params = "%f-%f-%f" % (x, y, z)
    sql_gen1 = "DELETE FROM polygons WHERE id = %s AND params = %s"
    sql_gen2_1 = """INSERT INTO polygons VALUES
  (%s,
   %s,
   NOW(),
   (SELECT """
    sql_gen2_2 = """ST_Buffer(ST_SimplifyPreserveTopology(ST_Buffer(ST_SnapToGrid(st_buffer(geom, %s), %s), 0), %s), 0))
    FROM polygons
    WHERE id = %s AND params = '0')
  );"""
    if x > 0:
      sql_gen2 = sql_gen2_1 + "ST_Union(ST_MakeValid(ST_SimplifyPreserveTopology(geom, 0.00001)), " + sql_gen2_2
    elif x == 0:
      sql_gen2 = sql_gen2_1 + "(" + sql_gen2_2
    else:
      sql_gen2 = sql_gen2_1 + "ST_Intersection(geom, " + sql_gen2_2
    PgCursor.execute(sql_gen1, (rel_id, params))
    try:
        PgCursor.execute(sql_gen2, (rel_id, params,
                                    x, y, z, rel_id ))
    except psycopg2.InternalError:
        show(u"Status: 500 Internal Server Error")
        utils.print_header("Polygon creation for id %d" % rel_id)
        show(u"Error while generating polygon.")
        show(u"Message from postgresql server:<br>")
        show(u"%s" % PgConn.notices)
        show(u"%s" % parse_pg_notices(PgConn.notices))
        sys.exit(0)

sql_list = """select id, params, timestamp, ST_NPoints(geom) AS npoints,
              ST_MaxDistance(geom, geom) AS length
         from polygons where id = %s
         ORDER BY params"""
PgCursor.execute(sql_list, (rel_id, ))

results = PgCursor.fetchall()

found_param_0 = False

for res in results:
    if res["params"] == "0":
        found_param_0 = True

if len(results) == 0 or refresh or not found_param_0:
    sys.stdout.flush()
    PgCursor.execute("DROP TABLE IF EXISTS tmp_way_poly_%d" % rel_id)
    PgCursor.execute("CREATE TABLE tmp_way_poly_%d (id integer, linestring geometry);" % rel_id)
    cmd = ("../tools/osmbin.py", "--dir", "/data/work/osmbin/data", "--read", "relation_geom", "%d" % rel_id)
    run = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    PgCursor.copy_from(run.stdout, "tmp_way_poly_%d" % rel_id)
    sql_create = "select create_polygon2(%s);"
    try:
        PgCursor.execute(sql_create, (rel_id, ))
    except psycopg2.InternalError:
        show(u"Status: 500 Internal Server Error")
        utils.print_header("Polygon creation for id %d" % rel_id)
        show(u"Error while generating polygon.")
        show(u"You could check the geometry through an analyser:<br>")
        show(u"<ul>")
        show(u"<li><a href='analyse-relation-open.py?id=%d'>analyser using an internal database</a>." % rel_id)
        show(u"<li><a href='http://ra.osmsurround.org/analyzeRelation?relationId=%d'>Relation analysis</a>." % rel_id)
        show(u"<li><a href='http://ra.osmsurround.org/analyzeMap?relationId=%d'>Relation analysis with map</a>." % rel_id)
#        show(u"<li><a href='http://analyser.openstreetmap.fr/cgi-bin/index.py?relation=%d'>analyser using OSM API (slower)</a>." % rel_id)
        show(u"</ul>")
        show(u"Message from postgresql server:<br>")
        show(u"%s" % parse_pg_notices(PgConn.notices))
        sys.exit(0)

    PgCursor.execute(sql_list, (rel_id, ))
        
    results = PgCursor.fetchall()

    import ast
    cmd = ("../tools/osmbin.py", "--dir", "/data/work/osmbin/data", "--read", "relation", "%d" % rel_id)
    run = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    j = ast.literal_eval(run.stdout.read().decode("utf-8"))
    if not j:
        show(u"Status: 500 Internal Server Error")
        utils.print_header("Polygon creation for id %d" % rel_id)
        show(u"Error while generating polygon.")
        show(u"Is relation present in OSM?<br>")
        show(u"<ul>")
        show(u"<li><a href='http://www.openstreetmap.org/relation/%d'>OSM</a>." % rel_id)
        show(u"</ul>")
        sys.exit(-1)

    PgCursor.execute("DELETE FROM relations WHERE id = %s", (rel_id, ))
    PgCursor.execute("INSERT INTO relations VALUES (%s, %s)", (rel_id, j["tag"]))

utils.print_header("Polygon creation for id %d" % rel_id)
show(u"<h1>%s</h1>" % ("List of available polygons for id = %d" % rel_id))

show(u"<table class='sortable'>")
show(u"  <tr>")
show(u"    <th class='sorttable_sorted'>%s<span id='sorttable_sortfwdind'>&nbsp;▾</span></th>" % ("params"))
show(u"    <th>%s</th>" % ("timestamp"))
show(u"    <th>%s</th>" % ("NPoints"))
show(u"    <th>%s</th>" % ("Length"))
show(u"    <th>%s</th>" % ("WKT"))
show(u"    <th>%s</th>" % ("GeoJSON"))
show(u"    <th>%s</th>" % ("poly"))
show(u"    <th>%s</th>" % ("Image"))
show(u"  </tr>")

for res in results:
    if res["params"] == "0":
        geom_length = res["length"]
    show(u"  <tr>")
    show(u"    <td>" + str(res["params"]) + "</td>")
    show(u"    <td>" + str(res["timestamp"]) + "</td>")
    show(u"    <td>" + str(res["npoints"]) + "</td>")
    show(u"    <td>" + str(res["length"]) + "</td>")
    show(u"    <td><a href='get_wkt.py?id=%d&amp;params=%s'>WKT</a></td>" % (rel_id, str(res["params"])))
    show(u"    <td><a href='get_geojson.py?id=%d&amp;params=%s'>GeoJSON</a></td>" % (rel_id, str(res["params"])))
    show(u"    <td><a href='get_poly.py?id=%d&amp;params=%s'>poly</a></td>" % (rel_id, str(res["params"])))
    show(u"    <td><a href='get_image.py?id=%d&amp;params=%s'>image</a></td>" % (rel_id, str(res["params"])))
    show(u"  </tr>")

show(u"</table>")

show(u"<br>\n")
show(u"<form method='POST' action=''>")
show(u"<input type='submit' value='Refresh original geometry' name='refresh'>")
show(u"</form>")

show(u"<h1>%s</h1>" % ("Generate a simplified polygon"))

show(u"<p>X, Y, Z are parameters for the following postgis equation. The default values are chosen according to the size of the original geometry to give a slighty bigger geometry, without too many nodes.</p>")
show(u"Note that:")
show(u"<ul>")
show(u"<li>X > 0 will give a polygon bigger than the original geometry, and guaranteed to contain it.")
show(u"<li>X = 0 will give a polygon similar to the original geometry.")
show(u"<li>X < 0 will give a polygon smaller than the original geometry, and guaranteed to be smaller.")
show(u"</ul>")

if geom_length >= 10:
    rec_x = 0.04
    rec_y = 0.01
    rec_z = 0.01
elif geom_length > 1:
    rec_x = 0.02
    rec_y = 0.005
    rec_z = 0.005
else:
    rec_x = 0.004
    rec_y = 0.001
    rec_z = 0.001

show(u"<form method='POST' action=''>")
show(u"<label for='x'>%s</label>" % "X")
show(u"<input type='text' name='x' id='x' value='%f'><br>" % rec_x)
show(u"<label for='y'>%s</label>" % "Y")
show(u"<input type='text' name='y' id='y' value='%f'><br>" % rec_y)
show(u"<label for='z'>%s</label>" % "Z")
show(u"<input type='text' name='z' id='z' value='%f'><br>" % rec_z)
show(u"<input type='submit' name='generate'>")
show(u"</form>")

show(u"<hr>")
show(u"SQL requests:")
show(u"<ul>")
show(u"<li>X > 0: <code>ST_Union(ST_MakeValid(ST_SimplifyPreserveTopology(geom, 0.00001)), ST_Buffer(ST_SimplifyPreserveTopology(ST_SnapToGrid(ST_Buffer(geom, X), Y), Z)))</code>")
show(u"<li>X = 0: <code>ST_Buffer(ST_SimplifyPreserveTopology(ST_SnapToGrid(ST_Buffer(geom, X), Y), Z)))</code>")
show(u"<li>X < 0: <code>ST_Intersection(geom, ST_Buffer(ST_SimplifyPreserveTopology(ST_SnapToGrid(ST_Buffer(geom, X), Y), Z)))</code>")
show(u"</ul>")

###########################################################################
utils.print_tail()

PgConn.commit()
PgConn.close()
