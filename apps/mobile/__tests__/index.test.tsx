import { render, screen } from '@testing-library/react-native';
import * as RN from 'react-native';
import HomeScreen from '../app/index';

describe('HomeScreen (M0 placeholder)', () => {
  afterEach(() => jest.restoreAllMocks());

  it('renders the product name as a header in the light theme', async () => {
    jest.spyOn(RN, 'useColorScheme').mockReturnValue('light');
    await render(<HomeScreen />);
    const title = screen.getByRole('header');
    expect(title).toHaveTextContent('InsmartFix');
    expect(screen.getByTestId('home-screen')).toHaveStyle({ backgroundColor: '#F4F6F8' });
  });

  it('follows the device dark setting (NFR-9)', async () => {
    jest.spyOn(RN, 'useColorScheme').mockReturnValue('dark');
    await render(<HomeScreen />);
    expect(screen.getByTestId('home-screen')).toHaveStyle({ backgroundColor: '#0D1417' });
  });
});
