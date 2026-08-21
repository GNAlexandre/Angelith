// Génère templates/reference.docx : le gabarit de styles utilisé par Pandoc
// pour produire le .docx final. Police Lucida Sans Unicode 12pt + styles
// nommés EXACTEMENT comme dans ton workflow : « Corps de texte », « Paragraphe »,
// « Pensée », plus « Encadré » pour les game-menus.
//
// Astuce : tu peux remplacer le reference.docx généré par UN DE TES PROPRES
// fichiers Vol.3 déjà mis en page. Pandoc lira tes styles réels (y compris le
// tiret cadratin automatique et l'italique automatique) et la sortie sera
// rigoureusement identique à ta charte existante.
//
// Usage : node tools/make_template.js   (écrit templates/reference.docx)

const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, HeadingLevel } = require("docx");

const FONT = "Lucida Sans Unicode";
const SIZE = 24; // demi-points → 12pt

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: SIZE } },
    },
    paragraphStyles: [
      // Base
      {
        id: "Normal",
        name: "Normal",
        run: { font: FONT, size: SIZE },
        paragraph: { spacing: { line: 276 } }, // ~1,15
      },
      // Narration. Pandoc envoie les paragraphes courants vers « Body Text »
      // (et « First Paragraph » pour le 1er après un titre). On définit les
      // trois pour que la narration tombe toujours sur la bonne graphie.
      {
        id: "BodyText",
        name: "Corps de texte",
        basedOn: "Normal",
        next: "BodyText",
        quickFormat: true,
        run: { font: FONT, size: SIZE },
        paragraph: {
          alignment: "both", // justifié
          indent: { firstLine: 340 }, // alinéa ~0,24"
          spacing: { line: 276 },
        },
      },
      {
        id: "FirstParagraph",
        name: "First Paragraph",
        basedOn: "BodyText",
        next: "BodyText",
        run: { font: FONT, size: SIZE },
        paragraph: { indent: { firstLine: 0 } }, // pas d'alinéa en ouverture de chapitre
      },
      // Dialogue. Le tiret cadratin est porté par le TEXTE (voir style_guide.md
      // et le flag dialogue_dash_in_text du config.yaml), pas par le style :
      // ça reste identique en .docx, .epub et .pdf.
      {
        id: "Paragraphe",
        name: "Paragraphe",
        basedOn: "Normal",
        next: "Paragraphe",
        quickFormat: true,
        run: { font: FONT, size: SIZE },
        paragraph: {
          alignment: "both",
          indent: { firstLine: 0 },
          spacing: { line: 276 },
        },
      },
      // Pensée intérieure → italique automatique (au niveau du style).
      {
        id: "Pensee",
        name: "Pensée",
        basedOn: "Normal",
        next: "BodyText",
        quickFormat: true,
        run: { font: FONT, size: SIZE, italics: true },
        paragraph: {
          alignment: "both",
          indent: { firstLine: 340 },
          spacing: { line: 276 },
        },
      },
      // Encadré game-menu (statut, succès, recette de craft) → gras + italique.
      {
        id: "Encadre",
        name: "Encadré",
        basedOn: "Normal",
        next: "BodyText",
        quickFormat: true,
        run: { font: FONT, size: SIZE, bold: true, italics: true },
        paragraph: {
          alignment: "left",
          indent: { left: 340, firstLine: 0 },
          spacing: { before: 80, after: 80, line: 276 },
        },
      },
      // Titres
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "BodyText",
        quickFormat: true,
        run: { font: FONT, size: 36, bold: true },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0, keepNext: true },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "FirstParagraph",
        quickFormat: true,
        run: { font: FONT, size: 30, bold: true, italics: true },
        paragraph: { spacing: { before: 120, after: 240 }, outlineLevel: 1, keepNext: true },
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 }, // A4
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      // Contenu minimal d'exemple : Pandoc ne garde que les définitions de styles.
      children: [
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Chapitre 1 :")] }),
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Titre")] }),
        new Paragraph({ style: "BodyText", children: [new TextRun("Narration.")] }),
        new Paragraph({ style: "Paragraphe", children: [new TextRun("— Dialogue.")] }),
        new Paragraph({ style: "Pensee", children: [new TextRun("Pensée.")] }),
        new Paragraph({ style: "Encadre", children: [new TextRun("[Encadré]")] }),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync("templates/reference.docx", buffer);
  console.log("OK -> templates/reference.docx");
});
