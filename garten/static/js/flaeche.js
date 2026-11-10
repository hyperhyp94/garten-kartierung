// Eigene Gartenfläche zeichnen oder abgehen.
import { erstelleEditor } from './editor.js';
import { seitenDaten } from './werkzeug.js';

const editor = erstelleEditor(seitenDaten(), { form: 'flaeche' });
document.getElementById('flaeche-form').addEventListener('sammeln', (ereignis) => {
  const lage = editor.geometrie();
  ereignis.detail.set('geometrie', lage ? JSON.stringify(lage) : '');
});
