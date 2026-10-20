// Under a busy machine (the full suite running in parallel) the default 1 s wait for an async UI change is the only
// timing in these tests that can fail without a real bug. Waiting longer costs nothing when the change comes quickly.
import { configure } from '@testing-library/react-native';

configure({ asyncUtilTimeout: 4000 });
