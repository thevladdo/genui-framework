# genui-framework

React components for GenUI zones: parts of a page whose content a GenUI backend generates for the person looking at it, checked against a schema, a URL whitelist and your pinned content before it renders.

The package needs a running GenUI backend. The backend and every option are documented in the [repository README](https://github.com/thevladdo/genui-framework#readme).

## Install

```bash
npm install genui-framework
```

`react` and `react-dom` 18 or later are peer dependencies. The package ships ESM and CommonJS builds behind an `exports` map, with bundled type declarations.

## Use

```tsx
import "genui-framework/styles.css";
import { GenUIZone } from "genui-framework";

<GenUIZone
  apiUrl="http://localhost:8000"
  zoneId="homepage-recommendations"
  basePrompt="Show recommended articles"
  preferredComponentType="bento"
  maxItems={6}
/>;
```

Without `userId` and `consent` the zone runs in anonymous mode: nothing is stored in the browser and no identifier is sent.

## License

Apache-2.0
