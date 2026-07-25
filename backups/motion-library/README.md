# Motion Library migration backup

`pre-change-source-1f517a5.tar.gz` contains the baseline versions of every
tracked file replaced or removed by the Motion Library migration, including all
six former packaged animation/gesture JSON files.

Baseline commit:

```text
1f517a52b6a1a2dbfcba51c2d589780e2fb55389
```

List the archive without extracting:

```bash
tar -tzf backups/motion-library/pre-change-source-1f517a5.tar.gz
```

The active application preserves legacy Motion and Gesture readers, so archived
files can still be opened or migrated without restoring them to package
resources.
