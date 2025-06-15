# Design decisions
This file contains documentation detailing the design decisions made during the development of grf-py. Its purpose is to offer insight into the decision-making process for those wishing to understand or revisit these choices later on. It's important to note that documenting a decision here doesn't imply immediate full compliance of the entire API with that decision. Instead, it signifies a gradual transition towards aligning with it.

## NML naming of properties
### Pros
- Smooth transition between NML and grf-py.
### Cons
- NML does a lot of magic with properties. Grf-py properties are more low-level and sometimes work differently.
- Some NML properties are named poorly and their role is not clear for people unfamiliar with NML.
- "Class" is a reserved word in Python so it's inconvenient to have a property named like that.
### Conclusion
Use NML naming where advantageous but remain flexible without excessive reliance on it.


## Zoom constants
As of version 0.3 use "human"/nml naming of constants. I.e. `ZOOM_4X` -> `ZOOM_2X` -> `ZOOM_NORMAL` -> `ZOOM_OUT_2X` -> `ZOOM_OUT_4X` -> `ZOOM_OUT_8X`. In OpenTTD code 4x zoom is called "normal" and that is extremely confusing, don't copy that.


## Versioning
Use `MAJOR.MINOR.PATCH` versioning with `MAJOR` currently at 0 to signify it's currently in early development and API is not stable at any point.
`PATCH` version changes with every release and can be done at any point regardless of the amount of changes included.
`MINOR` version can also be done at any point but signifies that at least one of significant features has been implemented. Otherwise it's no different from a patch release i.e. by no means it's more stable or anything.

### Significant features to implement
- ActionD code generation (ifs and parameters).
- Better Switch code generation (self/parent, modify placeholders, var60+ params, etc.)
- Better GRF string handling (grf-py decides range)
- Low level (properties and callbacks) API stabilization.
- High-level(lib) GRF feature completion.
- Achiving adequate amount of documentation.
- Fully reversible decompilation.

### Implemented significant features.
- **0.2.0** - GRF string and language API.
- **0.3.0** - Sprite caching (fingerprints).


## Keyword parameters
- Force keyword parameters for functions with many arguments to improve code redability.


## VarAction2 Subroutines/Procedures/Functions terminology

- NFO: procedure+subroutine (https://newgrf-specs.tt-wiki.net/wiki/VarAction2Advanced).
- NML: procedure (https://github.com/OpenTTD/nml/issues/105).
- Call them "function" in grf-py, "subrotine" is too archaic and "procedure" is deceptive as they return a value.


## Uncacheable sprite fingerpring
- Old approach: `return None`. Due to the high inheritability of sprite classes, special handling for None values introduces significant complexity and frequently leads to difficult-to-detect errors.
- New approach: `raise UncacheableSprite`. If it's uncacheable it's uncacheable, just raise exception and be done with it.
