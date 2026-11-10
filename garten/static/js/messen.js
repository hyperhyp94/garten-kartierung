// Abstände und Flächen messen. Nichts davon wird gespeichert.
import { erstelleEditor } from './editor.js';
import { seitenDaten } from './werkzeug.js';

erstelleEditor(seitenDaten(), { form: 'messen' });
