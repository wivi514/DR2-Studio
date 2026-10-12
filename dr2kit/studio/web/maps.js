// DR2 Studio's Maps view: a whole level in three.js, zone by zone (dr2kit/studio/maps_view.py).
//
// Python drives it through window.dr2 (QWebEnginePage.runJavaScript); the page talks back
// with console lines starting "dr2:" (maps_view.py reads them):
//   dr2:ready                      the page is up
//   dr2:status <text>              for the status line
//   dr2:want {zone, part, detail, script}   build/send one part of a zone: pieces, items, zombies, collision
//   dr2:pick {...}                 the user clicked something (a piece, an item, a marker)
//   dr2:camera {position, yaw}     where the camera is (for "Copy position")
//   dr2:edit {op, name, file, …}   editing (phase 11): move {position, rotation}, delete,
//                                  duplicate, undo, redo (studio/maps_edit.py answers with
//                                  dr2.itemState); zombies: zmove {path, position, yaw},
//                                  zdelete {path} (answered with dr2.setZombies);
//                                  buildings: pmove {zone, name, position, rotation,
//                                  scale}, phide {zone, name}, pcopy {zone, name}
//                                  (answered with dr2.pieceState)
//   dr2:place {point}              where to put a new item (the answer to dr2.askPlace,
//                                  or to dr2.placeAt: something dropped on the view)
//   dr2:focused {kind, name}       dr2.focus found and selected what it was asked for
//   dr2:drop {spec, point}         a row of the Place panel dropped on the view: what it
//                                  is (the drag's text, "dr2place:{…}") and the floor point
//                                  under the mouse (the page's own drag events, so the
//                                  point is exactly under it)
//   dr2:placecancel                Esc while placing
//
//   dr2.openLevel(meta, keep)      a level: zones, markers, nav mesh, start (convert/mapdata.py)
//   dr2.zoneReady(zone, part, detail, url)   a requested file is ready at url
//   dr2.zoneFailed(zone, part, detail, why)
//   dr2.setLayer(kind, on)         show or hide a layer ("pieces", "items", or a marker kind)
//   dr2.goTo(x, y, z, yaw)         put the camera there (eye height added), facing yaw
//   dr2.reload()                   drop every loaded zone and ask again (mods changed)
//   dr2.setView(eye, fwd, up, fovY) an exact camera (a recomp capture's, for comparing)
//   dr2.pickAt(x, y)               what a click at page pixel x, y would pick (tests)
//   dr2.setHour(h)                 time of day 0-23 (null: Studio's own neutral light)
//   dr2.setEditing(on)             edit mode: a clicked item, door or building gets move /
//                                  turn handles (T move, R turn, G size (buildings), F onto
//                                  the floor, Delete, Ctrl+D copy, Ctrl+Z / Ctrl+Y undo /
//                                  redo; arrow keys nudge it along the ground, Page Up /
//                                  Down up and down, [ ] turn, - = size; Shift: bigger
//                                  steps, Alt: smaller)
//   dr2.setGizmo(mode)             'translate', 'rotate' or 'scale' (as T, R, G)
//   dr2.setRotateAll(on)           turn about every axis, not only the up axis
//   dr2.pieceState([state…])       buildings after a change (mods/pieceedit.py
//                                  PieceState): moved, hidden, and the zone's copies (the
//                                  list of a zone's copies ends with a state with no name)
//   dr2.selectPiece(zone, name)    select a building (or a copy, <piece>#<n>)
//   dr2.pieceNames(zone)           the buildings of a loaded zone, copies included (tests)
//   dr2.selectGroup(zone, first, parts)   select a whole building: the handles move its
//                                  first piece and every part follows (dr2:edit pmove …
//                                  with group: true)
//   dr2.focus({kind, name, zone, position})   fly to a thing and select it when loaded
//                                  (the Hierarchy panel)
//   dr2.dragOver(x, y) / dr2.dragEnd()   something is dragged over the view: a marker
//                                  where it would land
//   dr2.placeAt(x, y)              answer with dr2:place: the floor point under page
//                                  pixel x, y
//   dr2.ghostScreen()              where the ring is drawn, in page pixels (tests)
//   dr2.startPlacing(label) / dr2.stopPlacing()   placing mode (a Place row clicked): the
//                                  ring follows the mouse, a click on the view answers
//                                  dr2:place there, Esc cancels
//   dr2.itemState([state…])        placed items after a change: moved, gone, or a new
//                                  model to load (url); kept, and applied again to every
//                                  zone file that loads later
//   dr2.askPlace()                 answer with dr2:place: the floor point in the middle
//                                  of the view
//   dr2.selectItem(name)           select a placed item by name (as a click would)
//   dr2.selectZombie(path)         select a single zombie or a clearing by block path
//   dr2.setEditedMarkers([marker…]) save points, doors and spawn points the mod adds
//                                  (placed from prefabs), drawn like the game's own
//   dr2.setZombies({crowds, zombie_spawns})   the missions' zombies as they are now:
//                                  single zombies (cones facing their way, "type ×n"),
//                                  respawn crates (their floor polygon), clearings (circles),
//                                  layer "zombie_spawn"; a single zombie or a clearing gets
//                                  the move / turn handles while editing
// Time of day (meta.lighting, convert/mapdata.py lighting): the lighting context whose
// area holds the camera gives, for the hour, the sky (the game's Skybox shader: a
// gradient by elevation, colour 1 at the horizon, 2 at the midpoint, 3 at the zenith),
// the fog, the key light and the ambient light from above / below; lightmapped surfaces
// keep their baked light, as in the game.
// The in-game map (meta.map: a picture and the world rectangle it covers, convert/
// mapdata.py map_picture) is drawn in the top-left corner with the camera on it (layer
// "overview"); a click there flies to that spot.
//
// Zones load nearest first: every zone with the small textures ("lod"), and the zones
// within NEAR metres of the camera at full size, swapped in place as the camera moves.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/examples/jsm/loaders/GLTFLoader.js';
import { applyLevelMaterials } from './levelmaterials.js';
import { TransformControls } from './vendor/three/examples/jsm/controls/TransformControls.js';

const NEAR = 40;              // metres from a zone's bounds: full-size textures inside this
const MAX_PENDING = 3;        // requests in flight at once (maps_view.BUILDERS threads)
const LABEL_RANGE = 90;       // labels further than this are hidden
const EYE = 1.7;

const statusEl = document.getElementById('status');
function post(kind, payload) {
  console.log('dr2:' + kind + (payload === undefined ? '' : ' ' + JSON.stringify(payload)));
}
function say(text) { statusEl.textContent = text; post('status', text); }

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
} catch (e) {
  say('no WebGL here (' + e.message + ')');
  throw e;
}
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87a0b4);
scene.add(new THREE.HemisphereLight(0xffffff, 0x50483c, 2.2));
const sun = new THREE.DirectionalLight(0xfff4e0, 1.6);
sun.position.set(0.4, 1, 0.3);
scene.add(sun);

// --- sky and time of day --------------------------------------------------------------
const skyUniforms = { c0: { value: new THREE.Color(0x87a0b4) }, c1: { value: new THREE.Color(0x87a0b4) },
  c2: { value: new THREE.Color(0x5070a0) }, mid: { value: 0.2 } };
const sky = new THREE.Mesh(new THREE.SphereGeometry(3000, 32, 16), new THREE.ShaderMaterial({
  uniforms: skyUniforms, side: THREE.BackSide, depthWrite: false, fog: false,
  vertexShader: `varying vec3 vDir; void main() { vDir = normalize(position);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: `uniform vec3 c0, c1, c2; uniform float mid; varying vec3 vDir;
    void main() {
      float t = asin(clamp(vDir.y, 0.0, 1.0)) / 1.5707963;     // elevation, 0..1
      float s = min(t, mid) / mid, r = max(t - mid, 0.0) / (1.0 - mid);
      vec3 c = c0 + s * ((c1 - c0) + r * (c2 - c1));
      gl_FragColor = vec4(c, 1.0);
      #include <colorspace_fragment>
    }`,
}));
sky.renderOrder = -10;
sky.visible = false;
scene.add(sky);
let hour = 12;
const hemi = scene.children.find(o => o.isHemisphereLight);
function lightAt(pos) {
  const L = (meta && meta.lighting) || [];
  for (const c of L) {
    if (!c.polygon || c.polygon.length < 3) continue;
    if (c.y && (pos.y < c.y[0] - 2 || pos.y > c.y[1] + 2)) continue;
    let inside = false;
    for (let i = 0, j = c.polygon.length - 1; i < c.polygon.length; j = i++) {
      const [xi, zi] = c.polygon[i], [xj, zj] = c.polygon[j];
      if ((zi > pos.z) !== (zj > pos.z) && pos.x < (xj - xi) * (pos.z - zi) / (zj - zi) + xi) inside = !inside;
    }
    if (inside) return c;
  }
  return L[0] || null;
}
let lastLight = null;
function applyLight() {
  if (hour === null || !meta || !meta.lighting || !meta.lighting.length) {
    if (lastLight !== 'none') {
      scene.background = new THREE.Color(0x87a0b4); scene.fog = null; sky.visible = false;
      hemi.color.set(0xffffff); hemi.groundColor.set(0x50483c); hemi.intensity = 2.2;
      sun.color.set(0xfff4e0); sun.intensity = 1.6; sun.position.set(0.4, 1, 0.3);
      lastLight = 'none';
    }
    return;
  }
  const c = lightAt(camera.position);
  const key = c.name + ':' + hour;
  if (key === lastLight) return;
  lastLight = key;
  const h = c.hours[hour];
  const col = v => new THREE.Color(Math.max(0, v[0]), Math.max(0, v[1]), Math.max(0, v[2]));
  skyUniforms.c0.value.copy(col(h.sky[0])); skyUniforms.c1.value.copy(col(h.sky[1]));
  skyUniforms.c2.value.copy(col(h.sky[2])); skyUniforms.mid.value = Math.max(0.01, h.sky_mid);
  sky.visible = true;
  scene.background = col(h.sky[0]);
  // the game's fog grows from start to end up to fog_max; three.js's linear fog grows to
  // 1, so its far end is stretched to reach fog_max at the game's end distance
  const span = Math.max(1, h.fog_end - h.fog_start) / Math.max(0.01, h.fog_max);
  scene.fog = h.fog_max > 0 ? new THREE.Fog(col(h.fog), h.fog_start, h.fog_start + span) : null;
  const k = col(h.key);
  sun.color.copy(k.r + k.g + k.b > 0 ? k.clone().multiplyScalar(1 / Math.max(k.r, k.g, k.b)) : k);
  sun.intensity = Math.max(k.r, k.g, k.b) * 0.8;
  sun.position.set(-h.key_dir[0], -h.key_dir[1], -h.key_dir[2]);
  hemi.color.copy(col(h.ambient.up).multiplyScalar(Math.PI * 4));
  hemi.groundColor.copy(col(h.ambient.down).multiplyScalar(Math.PI * 4));
  hemi.intensity = 1.0;
}

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 4000);
camera.rotation.order = 'YXZ';
let yaw = 0, pitch = 0, speed = 8;

// --- state --------------------------------------------------------------------------
let meta = null;
const zones = new Map();          // name -> {meta, box, pieces: slot, items: slot}
const layers = {};                // kind -> visible
const DEFAULT_ON = new Set(['pieces', 'items', 'door', 'item', 'spawn', 'map_area', 'map_point']);
const piecesRoot = new THREE.Group(), itemsRoot = new THREE.Group(), markerRoot = new THREE.Group();
const zombiesRoot = new THREE.Group();
const collisionRoot = new THREE.Group();
const addedRoot = new THREE.Group();     // items an edit added or turned into another item
const copiesRoot = new THREE.Group();    // copies of buildings an edit added (under pieces)
piecesRoot.add(copiesRoot);
scene.add(piecesRoot, itemsRoot, markerRoot, zombiesRoot, collisionRoot, addedRoot);
const markerGroups = {};          // kind -> Group
const labels = [];                // sprites, hidden when far
let pending = 0;
let selected = null, selBox = null;

function slot() { return { detail: null, wanted: null, object: null, asked: null }; }
const PARTS = ['pieces', 'items', 'zombies', 'collision'];
const ROOTS = {};

function layerOn(kind) { return layers[kind] !== undefined ? layers[kind] : DEFAULT_ON.has(kind); }

function dispose(obj) {
  obj.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    for (const m of [].concat(o.material || [])) {
      for (const k in m) if (m[k] && m[k].isTexture) m[k].dispose();
      m.dispose();
    }
  });
}

// --- markers ------------------------------------------------------------------------
const COLOURS = { spawn: 0x30e060, zombie_area: 0xe04040, map_area: 0x4090ff,
  zombie_spawn: 0xd02818, crate: 0xff8020, removal: 0x60c0ff,
  light_area: 0xffd040, trigger: 0xff40ff, sound_area: 0x40e0e0, map_point: 0xffa020,
  acoustics: 0xa0a0a0, waypoint: 0xffffff, navmesh: 0x40ff80 };

function label(text, colour, kind) {
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  const font = '28px sans-serif';
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 16;
  c.width = w; c.height = 40;
  ctx.font = font;
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillRect(0, 0, w, 40);
  ctx.fillStyle = '#' + new THREE.Color(colour).getHexString();
  ctx.fillText(text, 8, 29);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  // labels hide behind walls (depth test)
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: true,
                                         sizeAttenuation: false });
  const s = new THREE.Sprite(mat);
  s.scale.set(0.035 * w / 40, 0.035, 1);
  s.center.set(0.5, 0);
  s.renderOrder = 10;
  s.userData.isLabel = true;
  labels.push(s);
  return s;
}

function v3(a) { return new THREE.Vector3(a[0], a[1], a[2]); }

function polygonMarker(m, colour) {
  const g = new THREE.Group();
  const pts = m.polygon.map(v3);
  const h = m.height || 0;
  const lineMat = new THREE.LineBasicMaterial({ color: colour });
  g.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
  if (h > 0) {
    g.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(
      pts.map(p => p.clone().add(new THREE.Vector3(0, h, 0)))), lineMat));
    const verts = [];
    for (const p of pts) verts.push(p, p.clone().add(new THREE.Vector3(0, h, 0)));
    g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(verts), lineMat));
  }
  if (pts.length >= 3) {                     // a see-through floor, clickable
    const flat = pts.map(p => new THREE.Vector2(p.x, p.z));
    let tris = [];
    try { tris = THREE.ShapeUtils.triangulateShape(flat, []); } catch (e) { tris = []; }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(
      pts.flatMap(p => [p.x, p.y + 0.05, p.z]), 3));
    geo.setIndex(tris.flat());
    const fill = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: colour,
      transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false }));
    fill.userData.marker = m;
    g.add(fill);
  }
  const c = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).multiplyScalar(1 / pts.length);
  return [g, c.add(new THREE.Vector3(0, h || 1, 0))];
}

function pinMarker(m, colour, cone) {
  const g = new THREE.Group();
  g.position.copy(v3(m.position));
  const mat = new THREE.MeshBasicMaterial({ color: colour });
  const body = cone ? new THREE.Mesh(new THREE.ConeGeometry(0.35, 1.0, 12), mat)
                    : new THREE.Mesh(new THREE.SphereGeometry(0.3, 12, 8), mat);
  if (cone) {                                 // points the way the player will face (+Z)
    body.rotation.x = Math.PI / 2;
    body.position.y = 0.5;
    if (m.rotation) g.quaternion.set(...m.rotation);
  } else {
    body.position.y = 1.2;
  }
  body.userData.marker = m;
  g.add(body);
  g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(
    [new THREE.Vector3(), new THREE.Vector3(0, 1.2, 0)]), new THREE.LineBasicMaterial({ color: colour })));
  return [g, v3(m.position).add(new THREE.Vector3(0, 1.6, 0))];
}

function boxMarker(m, colour, size, quad) {
  const g = new THREE.Group();
  g.position.copy(v3(m.position));
  if (m.rotation) g.quaternion.set(...m.rotation);
  let geo;
  if (quad && m.polygon && m.polygon.length >= 3) {   // a trigger: its quad, extruded
    const r = parseFloat((m.props || {}).Radius || '1') || 1;
    const shape = new THREE.Shape(m.polygon.map(p => new THREE.Vector2(p[0] * r, p[2] * r)));
    geo = new THREE.ExtrudeGeometry(shape, { depth: m.height || 2, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
  } else {
    geo = new THREE.BoxGeometry(size[0] * 2, size[1] * 2, size[2] * 2);
  }
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({ color: colour }));
  const fill = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: colour,
    transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide }));
  fill.userData.marker = m;
  g.add(edges, fill);
  return [g, v3(m.position).add(new THREE.Vector3(0, 1.5, 0))];
}

function buildMarkers() {
  for (const k in markerGroups) { dispose(markerGroups[k]); markerRoot.remove(markerGroups[k]); delete markerGroups[k]; }
  labels.length = 0;
  for (const m of meta.markers || []) {
    const colour = COLOURS[m.kind] || 0xffffff;
    let made = null;
    if (m.polygon && m.polygon.length && m.kind !== 'trigger') made = polygonMarker(m, colour);
    else if (!m.position) continue;
    else if (m.kind === 'spawn') made = pinMarker(m, colour, true);
    else if (m.kind === 'trigger') made = boxMarker(m, colour, [1, 1, 1], true);
    else if (m.kind === 'sound_area' && m.scale) made = boxMarker(m, colour, m.scale, false);
    else made = pinMarker(m, colour, false);
    const [obj, at] = made;
    const text = m.label ? (m.kind === 'map_area' ? m.label.replace(/@\[[^\]]*\]\s*/g, '') : m.label)
      : (m.kind === 'trigger' && m.props && m.props.Level ? '→ ' + m.props.Level : m.name);
    if (['spawn', 'map_area', 'map_point', 'trigger', 'zombie_area'].includes(m.kind)) {
      const s = label(text, colour, m.kind);
      s.position.copy(at);
      obj.add(s);
      if (obj.position.lengthSq() > 0) s.position.sub(obj.position);
      if (m.rotation && (m.kind === 'spawn' || m.kind === 'trigger')) {
        s.position.applyQuaternion(obj.quaternion.clone().invert());
      }
    }
    const kind = m.kind;
    if (!markerGroups[kind]) {
      markerGroups[kind] = new THREE.Group();
      markerGroups[kind].visible = layerOn(kind);
      markerRoot.add(markerGroups[kind]);
    }
    markerGroups[kind].add(obj);
  }
  buildZombieSpawns();
  if (meta.navmesh) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(meta.navmesh.vertices, 3));
    geo.setIndex(meta.navmesh.triangles);
    geo.translate(0, 0.08, 0);
    const g = new THREE.Group();
    g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: COLOURS.navmesh,
      transparent: true, opacity: 0.25, depthWrite: false, side: THREE.DoubleSide })));
    g.add(new THREE.LineSegments(new THREE.WireframeGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0x208040, transparent: true, opacity: 0.5 })));
    g.visible = layerOn('navmesh');
    markerGroups.navmesh = g;
    markerRoot.add(g);
  }
}

// The missions' zombies (meta.zombie_spawns, convert/zombies.py MissionSpawn): one group,
// layer "zombie_spawn", rebuilt by dr2.setZombies after an edit.
function buildZombieSpawns() {
  const old = markerGroups.zombie_spawn;
  if (old) { dispose(old); markerRoot.remove(old); }
  const g = new THREE.Group();
  g.visible = layerOn('zombie_spawn');
  markerGroups.zombie_spawn = g;
  markerRoot.add(g);
  const shapes = {};
  for (const m of meta.markers || []) if (m.polygon && m.polygon.length) shapes[m.name.toLowerCase()] = m;
  for (const z of meta.zombie_spawns || []) {
    const p = z.props || {};
    const m = { kind: 'zombie_spawn', spawn: z.kind, name: z.path.split('/').pop(), path: z.path,
                mission: z.mission, when: z.when, props: p, file: 'missions.txt', line: z.line };
    let made = null, text = '';
    if (z.kind === 'single' && z.position) {
      const yaw = parseFloat(p.Rotation || '0') || 0;
      m.position = z.position;
      m.rotation = [0, Math.sin(yaw / 2), 0, Math.cos(yaw / 2)];
      made = pinMarker(m, COLOURS.zombie_spawn, true);
      const n = parseInt(p.NumberOfZombies || '1');
      text = `${p.ZombieType || '?'} ×${isNaN(n) ? 1 : n}` + (p.SpawnWithItem ? ` + ${p.SpawnWithItem}` : '')
        + (z.when ? ' (later)' : '');
    } else if (z.kind === 'removal' && z.position) {
      m.position = z.position;
      const r = parseFloat(p.Radius || '5') || 5;
      const pts = [];
      for (let i = 0; i < 48; i++) pts.push(new THREE.Vector3(Math.cos(i / 48 * 2 * Math.PI) * r, 0.1, Math.sin(i / 48 * 2 * Math.PI) * r));
      const grp = new THREE.Group();
      grp.position.copy(v3(z.position));
      grp.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: COLOURS.removal })));
      const disc = new THREE.Mesh(new THREE.CircleGeometry(r, 32), new THREE.MeshBasicMaterial({
        color: COLOURS.removal, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false }));
      disc.rotation.x = -Math.PI / 2;
      disc.position.y = 0.08;
      disc.userData.marker = m;
      grp.add(disc);
      made = [grp, v3(z.position).add(new THREE.Vector3(0, 1.2, 0))];
      text = `clears zombies (${r} m)`;
    } else if (z.kind === 'crate') {
      const shape = shapes[(p.ShapeName || '').toLowerCase()];
      if (!shape) continue;
      made = polygonMarker({ ...shape, ...m, polygon: shape.polygon, height: shape.height }, COLOURS.crate);
      text = `respawns ${p.ZombiesPerSpawnTime || '?'} every ${p.TimeBetweenSpawns || '?'} s`;
    }
    if (!made) continue;
    const [obj, at] = made;
    obj.userData.zombie = m;
    const s = label(text, COLOURS[z.kind === 'single' ? 'zombie_spawn' : z.kind], 'zombie_spawn');
    s.position.copy(at);
    obj.add(s);
    if (obj.position.lengthSq() > 0) s.position.sub(obj.position);
    if (m.rotation) s.position.applyQuaternion(obj.quaternion.clone().invert());
    g.add(obj);
  }
}

// Markers the mod adds (dr2.setEditedMarkers): drawn like the others, in their kind's
// group, tagged so the next call replaces them.
function buildEditedMarkers(list) {
  for (const k in markerGroups) {
    const g = markerGroups[k];
    for (const o of [...g.children]) if (o.userData.edited) { g.remove(o); dispose(o); }
  }
  for (const m of list) {
    const colour = COLOURS[m.kind] || 0xffffff;
    let made;
    if (m.kind === 'spawn' && m.position) made = pinMarker(m, colour, true);
    else if (m.kind === 'trigger' && m.position) made = boxMarker(m, colour, [1, 1, 1], true);
    else continue;
    const [obj, at] = made;
    obj.userData.edited = true;
    const isSave = m.props && m.props.ActionType === '4';
    const text = (isSave ? 'save point' : m.props && m.props.Level ? '→ ' + m.props.Level : m.name) + ' (your mod)';
    const s = label(text, colour, m.kind);
    s.position.copy(at).sub(obj.position);
    if (m.rotation) s.position.applyQuaternion(obj.quaternion.clone().invert());
    obj.add(s);
    if (!markerGroups[m.kind]) {
      markerGroups[m.kind] = new THREE.Group();
      markerGroups[m.kind].visible = layerOn(m.kind);
      markerRoot.add(markerGroups[m.kind]);
    }
    markerGroups[m.kind].add(obj);
  }
}

// --- the in-game map in the corner -----------------------------------------------------
const ov = document.getElementById('overview');
const ovCtx = ov.getContext('2d');
let ovImg = null;
let ovFloors = [];               // [{img, x, y, scale, when, height}]: the other floors
function setOverview() {
  ovImg = null;
  ovFloors = [];
  ov.style.display = 'none';
  if (!meta || !meta.map || !meta.map.url) return;
  for (const f of meta.map.floors || []) {
    const fi = new Image();
    fi.onload = () => ovFloors.push({ ...f, img: fi });
    fi.src = f.url;
  }
  const img = new Image();
  img.onload = () => {
    ovImg = img;
    ov.height = Math.round(ov.width * img.height / img.width);
    ov.style.display = layerOn('overview') ? 'block' : 'none';
  };
  img.src = meta.map.url;
}
function drawOverview() {
  if (!ovImg || ov.style.display === 'none') return;
  const [x0, x1, z0, z1] = meta.map.rect;
  ovCtx.drawImage(ovImg, 0, 0, ov.width, ov.height);
  // the floor you are on, as the game's map shows it: above the second-floor height or
  // below the basement height (fe_map_points), its picture over the darkened main one
  const feet = camera.position.y - EYE;
  const k = ov.width / ovImg.naturalWidth;
  for (const f of ovFloors) {
    if (f.height === null || f.height === undefined) continue;
    if ((f.when === 'above' && feet > f.height) || (f.when === 'below' && feet < f.height)) {
      ovCtx.fillStyle = 'rgba(0,0,0,0.45)';
      ovCtx.fillRect(0, 0, ov.width, ov.height);
      ovCtx.drawImage(f.img, f.x * k, f.y * k, f.img.naturalWidth * f.scale * k,
                      f.img.naturalHeight * f.scale * k);
      break;
    }
  }
  const px = (camera.position.x - x0) / (x1 - x0) * ov.width;
  const py = (camera.position.z - z0) / (z1 - z0) * ov.height;
  const dir = new THREE.Vector3(0, 0, -1).applyEuler(camera.rotation);
  ovCtx.save();
  ovCtx.translate(px, py);
  ovCtx.rotate(Math.atan2(dir.x, -dir.z));
  ovCtx.fillStyle = '#ff2020';
  ovCtx.strokeStyle = '#fff';
  ovCtx.beginPath();
  ovCtx.moveTo(0, -9); ovCtx.lineTo(6, 6); ovCtx.lineTo(0, 3); ovCtx.lineTo(-6, 6);
  ovCtx.closePath(); ovCtx.fill(); ovCtx.stroke();
  ovCtx.restore();
}
ov.addEventListener('click', e => {
  if (!meta || !meta.map) return;
  const [x0, x1, z0, z1] = meta.map.rect;
  const r = ov.getBoundingClientRect();
  const x = x0 + (e.clientX - r.left) / r.width * (x1 - x0);
  const z = z0 + (e.clientY - r.top) / r.height * (z1 - z0);
  camera.position.set(x, camera.position.y, z);
  schedule();
});

// --- zones --------------------------------------------------------------------------
function zoneDistance(z) { return z.box.distanceToPoint(camera.position); }

function desired(z) {
  if (z.meta.backdrop) return 'lod';
  return zoneDistance(z) < NEAR ? 'full' : 'lod';
}

function schedule() {
  if (!meta) return;
  const asks = [];
  for (const z of zones.values()) {
    for (const part of PARTS) {
      // editing snaps onto the collision mesh, so it is loaded (hidden) while editing
      if (part !== 'pieces' && !layerOn(part) && !(editing && part === 'collision')) continue;
      const want = part === 'collision' ? 'full' : desired(z);   // one size only
      const s = z[part];
      if (s.missing) continue;
      if (s.detail === want || s.asked === want) continue;
      asks.push({ z, part, want, d: zoneDistance(z) + (part === 'pieces' ? 0 : 1)
                  + (s.detail ? 1000 : 0) });     // what isn't shown at all goes first
    }
  }
  asks.sort((a, b) => a.d - b.d);
  for (const a of asks) {
    if (pending >= MAX_PENDING) break;
    const s = a.z[a.part];
    if (s.asked) continue;                       // one request per slot at a time
    s.asked = a.want;
    pending++;
    post('want', { zone: a.z.meta.name, part: a.part, detail: a.want, script: meta.script });
  }
}

function loadedCount() {
  let n = 0, full = 0;
  for (const z of zones.values()) { if (z.pieces.detail) n++; if (z.pieces.detail === 'full') full++; }
  return [n, full];
}

const loader = new GLTFLoader();

// Collision: see-through orange faces with their edges drawn, over the buildings, so
// both what you bump into and what's behind it stay visible.
function collisionLook(root) {
  const fill = new THREE.MeshBasicMaterial({ color: 0xff7319, transparent: true,
    opacity: 0.22, side: THREE.DoubleSide, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  const edges = new THREE.MeshBasicMaterial({ color: 0xffa040, wireframe: true,
    transparent: true, opacity: 0.55, depthWrite: false });
  const meshes = [];
  root.traverse(o => { if (o.isMesh) meshes.push(o); });
  for (const o of meshes) {
    for (const m of [].concat(o.material)) m.dispose();
    o.material = fill;
    const wire = new THREE.Mesh(o.geometry, edges);
    wire.renderOrder = 2;
    o.add(wire);
  }
}

function markMaterials(root) {
  root.traverse(o => {
    if (!o.isMesh) return;
    for (const m of [].concat(o.material)) {
      if (m.transparent || m.alphaTest > 0) m.side = THREE.DoubleSide;
    }
  });
}

window.dr2 = {
  openLevel(m, keep) {
    meta = m;
    for (const z of zones.values()) {
      for (const part of PARTS) if (z[part].object) { dispose(z[part].object); }
    }
    piecesRoot.clear(); itemsRoot.clear(); zombiesRoot.clear(); collisionRoot.clear();
    copiesRoot.clear(); piecesRoot.add(copiesRoot);
    pieceOverrides.clear(); pieceCopies.clear(); pendingFocus = null;
    detachGizmo();
    for (const o of addedRoot.children) dispose(o);
    addedRoot.clear(); added.clear(); overrides.clear();
    zones.clear();
    pending = 0;
    clearSelection();
    for (const zm of m.zones) {
      const box = new THREE.Box3(v3(zm.min), v3(zm.max));
      zones.set(zm.name, { meta: zm, box, pieces: slot(), items: slot(), zombies: slot(),
                              collision: slot() });
    }
    buildMarkers();
    setOverview();
    lastLight = null;
    if (!keep && m.start) {
      const p = m.start.position;
      let y = 0;
      if (m.start.rotation) {                    // the player's facing: a turn about Y
        const q = new THREE.Quaternion(...m.start.rotation);
        y = new THREE.Euler().setFromQuaternion(q, 'YXZ').y;
      }
      this.goTo(p[0], p[1], p[2], y);
    }
    say(`${m.level}: ${m.zones.length} zones; loading the nearest first…`);
    schedule();
  },
  zoneReady(name, part, detail, url) {
    pending = Math.max(0, pending - 1);
    const z = zones.get(name);
    if (!z) { schedule(); return; }
    const s = z[part];
    if (!url) {                                  // nothing there (a zone without items)
      s.missing = true; s.asked = null; schedule(); return;
    }
    loader.load(url, async gltf => {
      const obj = gltf.scene;
      obj.userData.zone = name;
      obj.userData.part = part;
      if (part === 'collision') collisionLook(obj);
      else {
        await applyLevelMaterials(gltf);         // lightmaps and blends, as the game
        markMaterials(obj);
      }
      const root = { pieces: piecesRoot, items: itemsRoot, zombies: zombiesRoot,
                     collision: collisionRoot }[part];
      if (s.object) {
        if (editTarget && isInside(editTarget.node, s.object)) detachGizmo();
        root.remove(s.object); dispose(s.object);
      }
      s.object = obj; s.detail = detail; s.asked = null;
      root.add(obj);
      if (part === 'items') for (const st of overrides.values()) applyOverride(st, obj);
      if (part === 'pieces') {
        obj.traverse(o => { if (o.userData.dr2_parked) o.visible = false; });   // hidden by a mod
        applyPieceOverrides(name); buildCopies(name);
      }
      if (pendingFocus) tryFocus();
      const [n, full] = loadedCount();
      say(`${meta.level}: ${n}/${zones.size} zones shown (${full} full size)`);
      schedule();
    }, undefined, err => {
      s.asked = null;
      say(`could not load ${name}: ${err.message || err}`);
      schedule();
    });
  },
  zoneFailed(name, part, detail, why) {
    pending = Math.max(0, pending - 1);
    const z = zones.get(name);
    if (z) { z[part].missing = true; z[part].asked = null; }
    say(`${name} (${part}): ${why}`);
    schedule();
  },
  setLayer(kind, on) {
    layers[kind] = !!on;
    if (kind === 'overview') ov.style.display = on && ovImg ? 'block' : 'none';
    else if (kind === 'pieces') piecesRoot.visible = !!on;
    else if (kind === 'items') { itemsRoot.visible = !!on; schedule(); }
    else if (kind === 'zombies') { zombiesRoot.visible = !!on; schedule(); }
    else if (kind === 'collision') { collisionRoot.visible = !!on; schedule(); }
    else if (markerGroups[kind]) markerGroups[kind].visible = !!on;
  },
  goTo(x, y, z, heading) {
    camera.position.set(x, y + EYE, z);
    if (heading !== null && heading !== undefined) { yaw = heading + Math.PI; pitch = -0.1; }
    applyLook();
    schedule();
  },
  reload() {
    if (meta) this.openLevel(meta, true);
  },
  setView(eye, fwd, up, fovY) {
    camera.position.set(...eye);
    camera.up.set(...up);
    camera.lookAt(eye[0] + fwd[0], eye[1] + fwd[1], eye[2] + fwd[2]);
    const e = new THREE.Euler().setFromQuaternion(camera.quaternion, 'YXZ');
    yaw = e.y; pitch = e.x;
    camera.rotation.copy(e);
    if (fovY) { camera.fov = fovY; camera.updateProjectionMatrix(); }
    schedule();
  },
  pickAt(x, y) { pick(x, y); },
  setHour(h) { hour = (h === null || h === undefined) ? null : h; lastLight = null; applyLight(); },
  setEditing(on) {
    editing = !!on;
    if (!editing) detachGizmo();
    else if (selected && selected.userData && selected.userData.dr2_item) attachGizmo(selected);
    schedule();
  },
  pieceState(states) {
    const zonesWithCopies = new Set(states.filter(s => s.copy).map(s => s.zone));
    for (const z of zonesWithCopies) pieceCopies.set(z, []);
    for (const st of states) {
      if (st.copy) { if (st.name) pieceCopies.get(st.zone).push(st); continue; }
      pieceOverrides.set(`${st.zone}/${st.name}`.toLowerCase(), st);
      applyPieceOverrides(st.zone);
    }
    for (const z of zonesWithCopies) buildCopies(z);
    updateSelBox();
  },
  pieceNames(zone) {
    const out = [], z = zones.get(zone);
    if (z && z.pieces.object) z.pieces.object.traverse(o => { if (o.userData.dr2_piece) out.push(o.userData.dr2_piece); });
    for (const o of copiesRoot.children) if (o.userData.dr2_zone === zone) out.push(o.userData.dr2_piece);
    return out;
  },
  selectGroup(zone, first, parts) {
    const lead = pieceNode(zone, first);
    if (!lead) return false;
    clearSelection();
    selected = lead;
    lead.updateMatrixWorld(true);
    const inv = lead.matrixWorld.clone().invert();
    const members = [];
    for (const n of parts) {
      const m = pieceNode(zone, n);
      if (!m || m === lead) continue;
      m.updateMatrixWorld(true);
      members.push({ node: m, rel: inv.clone().multiply(m.matrixWorld) });
    }
    editTarget = { node: lead, kind: 'piece', group: true, name: lead.userData.dr2_piece, zone, members };
    if (editing) gizmo.attach(lead);
    selBox = new THREE.Box3Helper(groupBox(), 0xffff00);
    selBox.material.depthTest = false;
    selBox.renderOrder = 20;
    scene.add(selBox);
    return true;
  },
  selectPiece(zone, name) {
    const n = pieceNode(zone, name);
    if (!n) return false;
    selectNode(n, { type: 'piece', name: n.userData.dr2_piece, vpath: n.userData.dr2_vpath,
                    index: n.userData.dr2_index, zone });
    return true;
  },
  focus(t) {
    if (t.position) {
      const p = v3(t.position);
      const back = new THREE.Vector3(0, 0, 1).applyEuler(new THREE.Euler(0, yaw, 0)).multiplyScalar(t.kind === 'piece' ? 14 : 5);
      camera.position.copy(p).add(back).add(new THREE.Vector3(0, t.kind === 'piece' ? 6 : 2.5, 0));
      camera.lookAt(p);
      const e = new THREE.Euler().setFromQuaternion(camera.quaternion, 'YXZ');
      yaw = e.y; pitch = e.x;
      applyLook();
      pivot = p.clone();
    }
    pendingFocus = t;
    tryFocus();
    schedule();
  },
  setGizmo(mode) { if (editTarget) setGizmoMode(mode); else gizmoWanted = mode; },
  setRotateAll(on) { rotateAll = !!on; setGizmoMode(gizmo.getMode()); },
  dragOver(x, y) {
    const hit = floorHit(x, y);
    if (!ghost) {
      ghost = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.06, 8, 32),
                             new THREE.MeshBasicMaterial({ color: 0xffd400, depthTest: false }));
      ghost.rotation.x = Math.PI / 2;
      ghost.renderOrder = 30;
      scene.add(ghost);
    }
    ghost.visible = !!hit;
    if (hit) ghost.position.copy(hit.point).add(new THREE.Vector3(0, 0.05, 0));
  },
  dragEnd() { if (ghost) ghost.visible = false; },
  startPlacing(label) {
    placing = label || 'it';
    say(`click in the view where ${placing} goes (Esc: cancel)`);
  },
  stopPlacing() { placing = null; this.dragEnd(); },
  ghostScreen() {                  // where the ring is drawn, in page pixels (tests)
    if (!ghost || !ghost.visible) return null;
    const p = ghost.position.clone().project(camera), r = renderer.domElement.getBoundingClientRect();
    return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height];
  },
  placeAt(x, y) {
    this.dragEnd();
    const hit = floorHit(x, y);
    if (!hit) { say('nothing there to put it on (drop it on the ground)'); return; }
    post('place', { point: hit.point.toArray().map(c => Math.round(c * 1000) / 1000) });
  },
  itemState(states) {
    for (const st of states) {
      overrides.set(st.name.toLowerCase(), st);
      applyOverride(st, null);
    }
  },
  askPlace() {
    const r = renderer.domElement.getBoundingClientRect();
    const hit = floorHit(r.left + r.width / 2, r.top + r.height / 2);
    const p = hit ? hit.point : camera.position.clone().add(
      new THREE.Vector3(0, 0, -4).applyEuler(camera.rotation)).setY(camera.position.y - EYE);
    post('place', { point: p.toArray().map(c => Math.round(c * 1000) / 1000) });
  },
  setEditedMarkers(list) { buildEditedMarkers(list || []); },
  setZombies(z) {
    if (!meta) return;
    const keep = editTarget && editTarget.path;
    if (keep) detachGizmo();
    meta.crowds = z.crowds; meta.zombie_spawns = z.zombie_spawns;
    labels.splice(0, labels.length, ...labels.filter(s => !isInside(s, markerGroups.zombie_spawn)));
    buildZombieSpawns();
    if (keep) {
      markerGroups.zombie_spawn.traverse(o => {
        if (o.userData.zombie && o.userData.zombie.path === keep && !editTarget) attachZombie(o);
      });
    }
  },
  selectZombie(path) {
    let found = null;
    if (markerGroups.zombie_spawn) markerGroups.zombie_spawn.traverse(o => {
      if (!found && o.userData.zombie && o.userData.zombie.path === path) found = o;
    });
    if (!found) return false;
    clearSelection();
    if (!(editing && attachZombie(found))) return false;
    post('pick', { type: 'marker', ...found.userData.zombie });
    return true;
  },
  selectItem(name) {
    const n = itemNodes(name, addedRoot)[0] || itemNodes(name).find(o => o.visible);
    if (n) pickNode(n);
    return !!n;
  },
  editInfo() {
    return { editing, target: editTarget && editTarget.name, kind: editTarget && editTarget.kind,
             mode: gizmo.getMode(), overrides: overrides.size, added: added.size,
             pieces: pieceOverrides.size, copies: copiesRoot.children.length,
             position: editTarget ? editTarget.node.getWorldPosition(new THREE.Vector3()).toArray() : null };
  },
  camera() {
    return { position: camera.position.toArray(), yaw };
  },
};

// --- camera: fly with the mouse and keys ------------------------------------------------
function applyLook() {
  camera.rotation.set(pitch, yaw, 0, 'YXZ');
}
const keys = new Set();
window.addEventListener('keydown', e => { keys.add(e.code); });
window.addEventListener('keyup', e => { keys.delete(e.code); });
window.addEventListener('blur', () => keys.clear());
let drag = null;
// --- placing: a Place row dragged onto the view, or clicked then a click on the view -------
let placing = null;               // what is being placed (a label), while in placing mode
function floorPoint(x, y) {
  const hit = floorHit(x, y);
  return hit ? hit.point.toArray().map(c => Math.round(c * 1000) / 1000) : null;
}
window.addEventListener('dragover', e => {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  window.dr2.dragOver(e.clientX, e.clientY);
});
window.addEventListener('dragleave', e => { if (!e.relatedTarget) window.dr2.dragEnd(); });
window.addEventListener('drop', e => {
  e.preventDefault();
  window.dr2.dragEnd();
  const text = (e.dataTransfer && e.dataTransfer.getData('text/plain')) || '';
  if (!text.startsWith('dr2place:')) return;
  const point = floorPoint(e.clientX, e.clientY);
  if (!point) { say('nothing there to put it on (drop it on the ground)'); return; }
  post('drop', { spec: JSON.parse(text.slice('dr2place:'.length)), point });
});
renderer.domElement.addEventListener('pointermove', e => {
  if (placing) window.dr2.dragOver(e.clientX, e.clientY);
});
window.addEventListener('keydown', e => {
  if (placing && e.code === 'Escape') {
    placing = null;
    window.dr2.dragEnd();
    say('placing cancelled');
    post('placecancel');
  }
});
renderer.domElement.addEventListener('pointerdown', e => {
  if (placing && e.button === 0) {                 // put it where the mouse is
    const point = floorPoint(e.clientX, e.clientY);
    if (!point) { say('nothing there to put it on: click on the ground'); return; }
    placing = null;
    window.dr2.dragEnd();
    drag = null;
    post('place', { point });
    e.stopImmediatePropagation();
    return;
  }
  if (editing && editTarget && (gizmo.axis !== null || gizmo.dragging)) {   // the handles
    drag = null;
    return;
  }
  drag = { x: e.clientX, y: e.clientY, moved: 0, button: e.button };
  renderer.domElement.setPointerCapture(e.pointerId);
});
renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());
let pivot = null;                 // orbit centre: the last clicked point
renderer.domElement.addEventListener('pointermove', e => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.moved += Math.abs(dx) + Math.abs(dy);
  drag.x = e.clientX; drag.y = e.clientY;
  if (drag.button === 2) {        // right button: orbit around the pivot
    const c = pivot || camera.position.clone().add(
      new THREE.Vector3(0, 0, -10).applyEuler(camera.rotation));
    const off = camera.position.clone().sub(c);
    off.applyAxisAngle(new THREE.Vector3(0, 1, 0), -dx * 0.005);
    const side = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), off).normalize();
    const tilted = off.clone().applyAxisAngle(side, dy * 0.005);
    if (Math.abs(tilted.clone().normalize().y) < 0.98) off.copy(tilted);
    camera.position.copy(c).add(off);
    camera.lookAt(c);
    const eul = new THREE.Euler().setFromQuaternion(camera.quaternion, 'YXZ');
    yaw = eul.y; pitch = eul.x;
    pivot = c;
  } else {                        // left button: look around
    yaw -= dx * 0.004;
    pitch = Math.max(-1.55, Math.min(1.55, pitch - dy * 0.004));
  }
  applyLook();
});
renderer.domElement.addEventListener('pointerup', e => {
  if (drag && drag.moved < 4 && drag.button === 0) pick(e.clientX, e.clientY);
  drag = null;
});

// --- editing (phase 11): move / turn / size handles, edit keys, what Python says changed -----
let editing = false;
let editTarget = null;            // {node, kind: 'item' | 'zombie' | 'piece', name, file | path | zone}
const overrides = new Map();      // lower name -> the last itemState for it
const added = new Map();          // lower name -> the object loaded for it (addedRoot)
const pieceOverrides = new Map(); // lower "zone/piece" -> the last pieceState for it
const pieceCopies = new Map();    // zone -> [pieceState of each copy]
let pendingFocus = null;          // dr2.focus waiting for its zone to load
let rotateAll = false;            // turn about every axis (dr2.setRotateAll)
let gizmoWanted = null;           // a mode asked for while nothing was selected
let ghost = null;                 // where a dragged thing would land
let nudgeTimer = null;
const gizmo = new TransformControls(camera, renderer.domElement);
gizmo.setSpace('world');
gizmo.setSize(0.9);
const gizmoHelper = gizmo.getHelper();
scene.add(gizmoHelper);
gizmo.addEventListener('objectChange', follow);
gizmo.addEventListener('dragging-changed', e => {
  if (!e.value && editTarget) sendMove(editTarget);     // a drag ended: save it
});
function setGizmoMode(mode) {
  if (mode === 'scale' && !(editTarget && editTarget.kind === 'piece')) {
    say('only buildings can change size (the game\'s item placements have no size)');
    mode = 'translate';
  }
  gizmo.setMode(mode);
  gizmo.setSpace(mode === 'scale' ? 'local' : 'world');
  const flat = mode === 'rotate' && !rotateAll;          // turn about the up axis only
  gizmo.showX = gizmo.showZ = !flat;
  gizmo.showY = true;
}
setGizmoMode('translate');
function isInside(o, root) { for (let p = o; p; p = p.parent) if (p === root) return true; return false; }
function attachGizmo(node) {
  const u = node.userData;
  editTarget = { node, kind: 'item', name: u.dr2_name, file: u.dr2_file };
  gizmo.attach(node);
  if (gizmo.getMode() === 'scale') setGizmoMode('translate');
}
function attachPiece(node, zone) {
  editTarget = { node, kind: 'piece', name: node.userData.dr2_piece, zone };
  gizmo.attach(node);
  if (gizmoWanted) { setGizmoMode(gizmoWanted); gizmoWanted = null; }
}
function attachZombie(group) {          // a single zombie's cone, or a clearing's circle
  const z = group.userData.zombie;
  if (!z || (z.spawn !== 'single' && z.spawn !== 'removal')) return false;
  editTarget = { node: group, kind: 'zombie', path: z.path, zombie: z };
  gizmo.attach(group);
  if (gizmo.getMode() === 'scale') setGizmoMode('translate');
  if (selBox) { scene.remove(selBox); selBox.geometry.dispose(); }
  selBox = new THREE.BoxHelper(group, 0xffff00);
  selBox.material.depthTest = false;
  selBox.renderOrder = 20;
  scene.add(selBox);
  return true;
}
function detachGizmo() { gizmo.detach(); editTarget = null; }
// A whole building: its parts keep their place relative to the first piece
function groupBox() {
  const box = new THREE.Box3().setFromObject(editTarget.node);
  for (const m of editTarget.members) box.expandByObject(m.node);
  return box;
}
function follow() {
  const t = editTarget;
  if (t && t.group) {
    t.node.updateMatrixWorld(true);
    for (const m of t.members) {
      const world = t.node.matrixWorld.clone().multiply(m.rel);
      const local = m.node.parent ? m.node.parent.matrixWorld.clone().invert().multiply(world) : world;
      local.decompose(m.node.position, m.node.quaternion, m.node.scale);
    }
  }
  updateSelBox();
}
function updateSelBox() {
  if (!selBox) return;
  if (selBox.isBox3Helper && editTarget && editTarget.group) selBox.box.copy(groupBox());
  else if (selBox.update) selBox.update();
}
const r3 = c => Math.round(c * 1000) / 1000;
const r4 = c => Math.round(c * 10000) / 10000;
function sendMove(t) {
  const p = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
  t.node.getWorldPosition(p);
  t.node.getWorldQuaternion(q);
  t.node.getWorldScale(sc);
  if (t.kind === 'zombie') {                      // a zombie: place and facing (radians)
    const yaw = new THREE.Euler().setFromQuaternion(q, 'YXZ').y;
    post('edit', { op: 'zmove', path: t.path, position: p.toArray().map(r3),
                   yaw: t.zombie.spawn === 'single' ? r3(yaw) : null });
    return;
  }
  if (t.kind === 'piece') {
    post('edit', { op: 'pmove', zone: t.zone, name: t.name, position: p.toArray().map(r3),
                   rotation: [q.x, q.y, q.z, q.w].map(r4), scale: sc.toArray().map(r4),
                   group: !!t.group });
    return;
  }
  post('edit', { op: 'move', name: t.name, file: t.file, position: p.toArray().map(r3),
                 rotation: [q.x, q.y, q.z, q.w].map(r4) });
}
// Arrow keys and [ ] / - =: small steps, saved once the keys rest (one undo step)
function saveSoon() {
  clearTimeout(nudgeTimer);
  const t = editTarget;
  nudgeTimer = setTimeout(() => { if (t && t === editTarget) sendMove(t); }, 450);
}
function groundAxis(v) {          // a direction snapped to the nearest world axis on the ground
  return Math.abs(v.x) > Math.abs(v.z) ? new THREE.Vector3(Math.sign(v.x), 0, 0)
                                       : new THREE.Vector3(0, 0, Math.sign(v.z) || 1);
}
function nudge(code, step) {
  const fwd = groundAxis(new THREE.Vector3(0, 0, -1).applyEuler(camera.rotation));
  const right = groundAxis(new THREE.Vector3(1, 0, 0).applyEuler(camera.rotation));
  const d = { ArrowUp: fwd, ArrowDown: fwd.clone().negate(), ArrowRight: right,
              ArrowLeft: right.clone().negate(), PageUp: new THREE.Vector3(0, 1, 0),
              PageDown: new THREE.Vector3(0, -1, 0) }[code];
  const n = editTarget.node;
  const world = n.getWorldPosition(new THREE.Vector3()).addScaledVector(d, step);
  n.position.copy(n.parent ? n.parent.worldToLocal(world) : world);
  follow();
  saveSoon();
}
function turn(degrees) {
  const n = editTarget.node;
  const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), degrees * Math.PI / 180);
  const wq = n.getWorldQuaternion(new THREE.Quaternion()).premultiply(q);
  if (n.parent) wq.premultiply(n.parent.getWorldQuaternion(new THREE.Quaternion()).invert());
  n.quaternion.copy(wq);
  follow();
  saveSoon();
}
function grow(f) {
  if (editTarget.kind !== 'piece') { say('only buildings can change size'); return; }
  editTarget.node.scale.multiplyScalar(f);
  follow();
  saveSoon();
}
// The floor under a point: a ray down onto the collision mesh (what the game stands on),
// or onto the buildings while the collision isn't loaded.
const down = new THREE.Raycaster();
function floorBelow(p, skip) {
  down.set(p.clone().add(new THREE.Vector3(0, 1.5, 0)), new THREE.Vector3(0, -1, 0));
  const roots = collisionRoot.children.length ? [collisionRoot] : [piecesRoot];
  const hits = down.intersectObjects(roots, true).filter(h => h.object.isMesh &&
    (!skip || !isInside(h.object, skip)) && !(h.object.material && h.object.material.wireframe));
  return hits.length ? hits[0].point : null;
}
function floorHit(x, y) {
  const r = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1,
                                      -((y - r.top) / r.height) * 2 + 1), camera);
  const roots = collisionRoot.children.length ? [collisionRoot, piecesRoot] : [piecesRoot];
  const hits = ray.intersectObjects(roots, true).filter(h => h.object.isMesh &&
    visibleChain(h.object) && !(h.object.material && h.object.material.wireframe));
  return hits[0] || null;
}
function snapToFloor(t) {
  const box = new THREE.Box3().setFromObject(t.node);
  const at = new THREE.Vector3();
  t.node.getWorldPosition(at);
  const floor = floorBelow(new THREE.Vector3(at.x, box.min.y, at.z), t.node);
  if (!floor) { say('no floor under it (load the zone first)'); return; }
  const world = at.clone().setY(at.y + floor.y - box.min.y);
  t.node.position.copy(t.node.parent ? t.node.parent.worldToLocal(world) : world);
  follow();
  sendMove(t);
}
function itemNodes(name, within) {
  const out = [], low = name.toLowerCase();
  (within || itemsRoot).traverse(o => {
    if (o.userData && o.userData.dr2_name && o.userData.dr2_name.toLowerCase() === low) out.push(o);
  });
  return out;
}
function setTransform(node, st) {
  const world = v3(st.position);
  node.position.copy(node.parent ? node.parent.worldToLocal(world) : world);
  if (st.rotation) {
    const q = new THREE.Quaternion(...st.rotation).normalize();
    if (node.parent) {
      const pq = new THREE.Quaternion();
      node.parent.getWorldQuaternion(pq);
      q.premultiply(pq.invert());
    }
    node.quaternion.copy(q);
  }
  if (st.scale) node.scale.set(...st.scale);
}
// Show one item as the last change left it; ``within`` (a zone file just loaded) only
// hides or moves its own nodes (a model to load is loaded once, by itemState).
function applyOverride(st, within) {
  const key = st.name.toLowerCase();
  const originals = itemNodes(st.name, within || itemsRoot);
  if (st.removed) {
    for (const n of originals) n.visible = false;
    if (!within && added.has(key)) { const o = added.get(key); addedRoot.remove(o); dispose(o); added.delete(key); }
    if (editTarget && editTarget.kind === 'item' && editTarget.name.toLowerCase() === key) { detachGizmo(); clearSelection(); }
    return;
  }
  if (st.url && !within) {                       // a new model: load it, hide the original
    loader.load(st.url, async gltf => {
      await applyLevelMaterials(gltf);
      markMaterials(gltf.scene);
      if (added.has(key)) { const o = added.get(key); addedRoot.remove(o); dispose(o); }
      added.set(key, gltf.scene);
      addedRoot.add(gltf.scene);
      for (const n of itemNodes(st.name)) n.visible = false;
      const node = itemNodes(st.name, gltf.scene)[0];
      if (node && editing) {
        pickNode(node);
        // a new item stands on the floor by its bottom (a Humvee's origin is its middle)
        if (st.snap && editTarget) snapToFloor(editTarget);
      }
    });
    return;
  }
  if (added.has(key) || (overrides.get(key) || {}).url) {    // shown by its added copy
    for (const n of originals) n.visible = false;
    if (within) return;
    for (const n of itemNodes(st.name, addedRoot)) setTransform(n, st);
  } else {
    for (const n of originals) { setTransform(n, st); n.visible = true; }
  }
  updateSelBox();
}
// Buildings: a zone's piece by name (or a copy, <piece>#<n>, in copiesRoot)
// (a building another mod hid, parked under the level, is not returned: its place there
// isn't one to edit from; one the edited mod hid has its state, so it is)
function pieceNode(zone, name) {
  const low = name.toLowerCase();
  let found = null;
  if (!pieceOverrides.has(`${zone}/${name}`.toLowerCase())) {
    const z = zones.get(zone);
    let parked = false;
    if (z && z.pieces.object) z.pieces.object.traverse(o => {
      if (o.userData.dr2_parked && o.userData.dr2_piece && o.userData.dr2_piece.toLowerCase() === low) parked = true;
    });
    if (parked) return null;
  }
  const z = zones.get(zone);
  const within = name.includes('#') ? copiesRoot : (z && z.pieces.object);
  if (!within) return null;
  within.traverse(o => {
    if (!found && o.userData.dr2_piece && o.userData.dr2_piece.toLowerCase() === low &&
        (!name.includes('#') || o.userData.dr2_zone === zone)) found = o;
  });
  return found;
}
function applyPieceOverrides(zone) {
  const z = zones.get(zone);
  if (!z || !z.pieces.object) return;
  for (const st of pieceOverrides.values()) {
    if (st.zone !== zone) continue;
    const n = pieceNode(zone, st.name);
    if (!n) continue;
    setTransform(n, st);
    n.visible = !st.hidden;
    if (st.hidden && editTarget && editTarget.node === n) { detachGizmo(); clearSelection(); }
  }
}
function buildCopies(zone) {
  const keep = editTarget && editTarget.kind === 'piece' && editTarget.name.includes('#') &&
    editTarget.zone === zone ? editTarget.name : null;
  if (keep) { detachGizmo(); clearSelection(); }
  for (const o of [...copiesRoot.children]) {
    if (o.userData.dr2_zone === zone) copiesRoot.remove(o);    // shared geometry: no dispose
  }
  const z = zones.get(zone);
  if (!z || !z.pieces.object) return;
  for (const st of pieceCopies.get(zone) || []) {
    const src = pieceNode(zone, st.piece);
    if (!src) continue;
    const c = src.clone(true);
    c.userData = { ...src.userData, dr2_piece: st.name, dr2_copy: true, dr2_zone: zone };
    c.visible = true;
    setTransform(c, st);
    copiesRoot.add(c);
  }
  if (keep && editing) {
    const n = pieceNode(zone, keep);
    if (n) selectNode(n, { type: 'piece', name: keep, vpath: n.userData.dr2_vpath, zone });
  }
}
function selectNode(node, info) {
  clearSelection();
  selected = node;
  selBox = new THREE.BoxHelper(node, 0xffff00);
  selBox.material.depthTest = false;
  selBox.renderOrder = 20;
  scene.add(selBox);
  if (editing && info.type === 'piece') attachPiece(node, info.zone);
  else if (editing && node.userData.dr2_item) attachGizmo(node);
  post('pick', info);
}
function pickNode(node) {
  const u = node.userData;
  selectNode(node, { type: u.dr2_kind || 'item', name: u.dr2_name, item: u.dr2_item,
                     vpath: u.dr2_vpath, file: u.dr2_file, line: u.dr2_line });
}
// dr2.focus: select the thing once its zone is loaded
function tryFocus() {
  const t = pendingFocus;
  if (!t) return;
  let ok = false;
  if (t.kind === 'piece') {
    const z = zones.get(t.zone);
    ok = window.dr2.selectPiece(t.zone, t.name) || !!(z && z.pieces.object);  // loaded: done
  }
  else if (t.kind === 'zombie') ok = window.dr2.selectZombie(t.name);
  else if (t.kind === 'item' || t.kind === 'door') ok = window.dr2.selectItem(t.name);
  else ok = true;                                      // a marker: flying there is all
  if (ok) { pendingFocus = null; post('focused', { kind: t.kind, name: t.name }); }
}
window.addEventListener('keydown', e => {
  if (!editing) return;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.code === 'KeyZ') { post('edit', { op: e.shiftKey ? 'redo' : 'undo' }); e.preventDefault(); return; }
  if (ctrl && e.code === 'KeyY') { post('edit', { op: 'redo' }); e.preventDefault(); return; }
  if (!editTarget) return;
  const t = editTarget;
  const big = e.shiftKey, small = e.altKey;
  if (/^Arrow|^Page(Up|Down)$/.test(e.code)) {
    nudge(e.code, big ? 1 : small ? 0.01 : 0.1);
    e.preventDefault();
    return;
  }
  if (e.code === 'BracketLeft' || e.code === 'BracketRight') {
    turn((e.code === 'BracketLeft' ? 1 : -1) * (big ? 90 : small ? 1 : 15));
    if (t.kind === 'zombie' && t.zombie.spawn !== 'single') say('a clearing has no facing');
    return;
  }
  if (e.code === 'Minus' || e.code === 'Equal' || e.code === 'NumpadSubtract' || e.code === 'NumpadAdd') {
    const up = e.code === 'Equal' || e.code === 'NumpadAdd';
    grow(up ? (big ? 2 : small ? 1.01 : 1.1) : 1 / (big ? 2 : small ? 1.01 : 1.1));
    return;
  }
  if (e.code === 'KeyT') setGizmoMode('translate');
  else if (e.code === 'KeyR') setGizmoMode('rotate');
  else if (e.code === 'KeyG') setGizmoMode('scale');
  else if (e.code === 'KeyF') snapToFloor(t);
  else if (e.code === 'Delete' || e.code === 'Backspace') {
    if (t.kind === 'zombie') post('edit', { op: 'zdelete', path: t.path });
    else if (t.kind === 'piece') post('edit', { op: 'phide', zone: t.zone, name: t.name, group: !!t.group });
    else post('edit', { op: 'delete', name: t.name, file: t.file });
  } else if (ctrl && e.code === 'KeyD' && t.kind !== 'zombie') {
    if (t.kind === 'piece') post('edit', { op: 'pcopy', zone: t.zone, name: t.name, group: !!t.group });
    else post('edit', { op: 'duplicate', name: t.name, file: t.file });
    e.preventDefault();
  }
});
renderer.domElement.addEventListener('wheel', e => {
  speed = Math.max(0.5, Math.min(200, speed * (e.deltaY < 0 ? 1.25 : 0.8)));
  say(`speed ${speed.toFixed(1)} m/s`);
  e.preventDefault();
}, { passive: false });

let lastTime = performance.now();
let sinceSchedule = 0, sinceCamera = 0;
function move(dt) {
  const f = (keys.has('ShiftLeft') || keys.has('ShiftRight') ? 4 : 1) * speed * dt;
  const fwd = new THREE.Vector3(0, 0, -1).applyEuler(camera.rotation);
  const right = new THREE.Vector3(1, 0, 0).applyEuler(camera.rotation);
  const v = new THREE.Vector3();
  const arrows = !(editing && editTarget);      // while editing, the arrows nudge the selection
  if (keys.has('KeyW') || (arrows && keys.has('ArrowUp'))) v.add(fwd);
  if (keys.has('KeyS') || (arrows && keys.has('ArrowDown'))) v.sub(fwd);
  if (keys.has('KeyD') || (arrows && keys.has('ArrowRight'))) v.add(right);
  if (keys.has('KeyA') || (arrows && keys.has('ArrowLeft'))) v.sub(right);
  if (keys.has('KeyE') || (arrows && keys.has('PageUp'))) v.y += 1;
  if (keys.has('KeyQ') || (arrows && keys.has('PageDown'))) v.y -= 1;
  if (v.lengthSq() > 0) camera.position.addScaledVector(v.normalize(), f);
}

// --- picking ----------------------------------------------------------------------------
const ray = new THREE.Raycaster();
function clearSelection() {
  if (selBox) { scene.remove(selBox); selBox.geometry.dispose(); selBox = null; }
  selected = null;
}
function visibleChain(o) {
  for (let p = o; p; p = p.parent) if (!p.visible) return false;
  return true;
}
function pick(x, y) {
  const r = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1,
                                      -((y - r.top) / r.height) * 2 + 1), camera);
  ray.camera = camera;
  const hits = ray.intersectObjects([piecesRoot, itemsRoot, addedRoot, markerRoot], true)
    .filter(h => !h.object.userData.isLabel && h.object.isMesh && visibleChain(h.object));
  clearSelection();
  for (const h of hits) {
    let info = null, target = null;
    for (let o = h.object; o && !info; o = o.parent) {
      const u = o.userData || {};
      if (u.marker) { info = { type: 'marker', ...u.marker }; delete info.polygon; target = h.object.parent; }
      else if (u.zombie) { info = { type: 'marker', ...u.zombie }; target = o; }
      else if (u.dr2_piece) { info = { type: 'piece', name: u.dr2_piece, vpath: u.dr2_vpath, index: u.dr2_index }; target = o; }
      else if (u.dr2_zombie) { info = { type: 'zombie', name: u.dr2_zombie, vpath: u.dr2_vpath, area: u.dr2_area, mission: u.dr2_mission, line: u.dr2_line, path: u.dr2_path }; target = o; }
      else if (u.dr2_item) { info = { type: u.dr2_kind || 'item', name: u.dr2_name, item: u.dr2_item, vpath: u.dr2_vpath, file: u.dr2_file, line: u.dr2_line }; target = o; }
    }
    if (!info) continue;
    for (let o = h.object; o; o = o.parent) {
      const u = o.userData || {};
      if (u.zone || u.dr2_zone) { info.zone = u.zone || u.dr2_zone; break; }
    }
    let zombieGroup = null;
    for (let o = target; o; o = o.parent) if (o.userData && o.userData.zombie) { zombieGroup = o; break; }
    if (editing && target && target.userData && target.userData.dr2_item) attachGizmo(target);
    else if (editing && info.type === 'piece' && info.zone) attachPiece(target, info.zone);
    else if (editing && zombieGroup && attachZombie(zombieGroup)) {
      info = { type: 'marker', ...zombieGroup.userData.zombie };
      post('pick', info);
      return;
    }
    else detachGizmo();
    if (info.type === 'piece' && target.userData.dr2_copy) info.copy = true;
    info.point = h.point.toArray().map(c => Math.round(c * 1000) / 1000);
    pivot = h.point.clone();
    selected = target;
    selBox = new THREE.BoxHelper(target, 0xffff00);
    selBox.material.depthTest = false;
    selBox.renderOrder = 20;
    scene.add(selBox);
    post('pick', info);
    return;
  }
  detachGizmo();
  post('pick', { type: 'none', point: hits.length ? hits[0].point.toArray() : null });
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const tmp = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  const now = performance.now();
  const dt = Math.min((now - lastTime) / 1000, 0.1);
  lastTime = now;
  move(dt);
  sinceSchedule += dt; sinceCamera += dt;
  if (sinceSchedule > 0.3) { sinceSchedule = 0; schedule(); }
  if (sinceCamera > 1.0) {
    sinceCamera = 0;
    post('camera', { position: camera.position.toArray().map(c => Math.round(c * 100) / 100), yaw });
  }
  for (const s of labels) {
    s.getWorldPosition(tmp);
    s.visible = tmp.distanceTo(camera.position) < LABEL_RANGE;
  }
  sky.position.copy(camera.position);
  applyLight();
  renderer.render(scene, camera);
  drawOverview();
});
applyLook();
say('ready');
post('ready');
