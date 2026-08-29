import Reveal from 'reveal.js';
import Notes from 'reveal.js/plugin/notes/notes.esm.js';

import 'reveal.js/dist/reveal.css';
import './css/theme.css';

// The chain is the map of the talk. Section slides carry a compact strip of it
// so the audience always knows which segment is being proved.
const CHAIN = ['detect', 'retrieve', 'explain', 'validate', 'approve', 'write', 'prove'];

for (const bar of document.querySelectorAll('.chainbar')) {
    const at = Number(bar.dataset.at);
    bar.innerHTML = CHAIN.map(
        (name, i) => `<span class="${i === at ? 'on' : ''}">${name}</span>`,
    ).join('');
}

Reveal.initialize({
    width: 1600,
    height: 900,
    margin: 0.03,
    minScale: 0.2,
    maxScale: 2.0,
    hash: true,
    slideNumber: 'c/t',
    showSlideNumber: 'speaker',
    transition: 'fade',
    transitionSpeed: 'fast',
    backgroundTransition: 'fade',
    controls: false,
    progress: true,
    center: false,
    plugins: [Notes],
});
