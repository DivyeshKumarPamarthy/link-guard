// Ready-made links for the live demo (the scenarios planned for T4.2's demo script), so nobody
// types them in front of the panel. Every link points at the local demo server (a/b/c.demo.test map to 127.0.0.1 in
// the backend's demo profile) or at an address the backend must refuse. They are shown only
// when the app runs with `npm run dev:demo` (SHOW_DEMO_LINKS in config.ts); a normal build
// never shows them. Each link is still checked for real by the backend: no result is faked.

export interface DemoLink {
  /** What the link demonstrates, in plain words. */
  label: string
  url: string
}

export const DEMO_LINKS: DemoLink[] = [
  { label: 'A genuine PDF', url: 'http://a.demo.test:8081/f/sample.pdf' },
  {
    label: 'A Windows program named movie.mp4, behind two redirects',
    url: 'http://a.demo.test:8081/redirect/chain?n=2&to=/disguised/movie.mp4',
  },
  { label: 'A double extension: invoice.pdf.exe', url: 'http://a.demo.test:8081/disguised/invoice.pdf.exe' },
  { label: 'A 200 MB file, only the first 5 MB read', url: 'http://a.demo.test:8081/big?range=yes' },
  { label: 'The cloud metadata address', url: 'http://169.254.169.254/latest/meta-data/' },
  { label: 'A redirect into this computer', url: 'http://a.demo.test:8081/redirect/internal' },
  { label: 'A web page served as file.pdf', url: 'http://a.demo.test:8081/disguised/file.pdf' },
  { label: 'A server with the wrong certificate', url: 'https://a.demo.test:8444/f/sample.png' },
  { label: 'A magnet link', url: 'magnet:?xt=urn:btih:0123456789abcdef' },
]
