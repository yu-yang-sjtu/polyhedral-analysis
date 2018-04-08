import unittest
from unittest.mock import Mock, mock_open, patch
from polyhedral_analysis.trajectory import Trajectory, read_config_numbers_from_xdatcar
from polyhedral_analysis.polyhedra_recipe import PolyhedraRecipe
from polyhedral_analysis.configuration import Configuration
from pymatgen.io.vasp.outputs import Xdatcar
from pymatgen import Structure

class TestTrajectoryInit( unittest.TestCase ):

    @patch( 'polyhedral_analysis.trajectory.read_config_numbers_from_xdatcar' )
    @patch( 'polyhedral_analysis.trajectory.Configuration' )
    @patch( 'polyhedral_analysis.trajectory.Xdatcar' )
    def test_trajectory_is_initialised( self, MockXdatcar, MockConfiguration, 
                                        mock_read_config_numbers ):
        mock_read_config_numbers.return_value = [ 0, 1 ]
        mock_xdatcar = Mock( spec=Xdatcar )
        MockXdatcar.return_value = mock_xdatcar
        mock_configurations = [ Mock( spec=Configuration ), Mock( spec=Configuration ) ]
        mock_xdatcar.structures = [ Mock( spec=Structure ), Mock( spec=Structure ) ]
        MockConfiguration.side_effect = mock_configurations
        mock_recipe = Mock( spec=PolyhedraRecipe )
        trajectory = Trajectory( xdatcar='test_inputs/example_XDATCAR', recipes=[ mock_recipe ] )
        self.assertEqual( len( trajectory.configurations ), 2 ) 
        self.assertEqual( trajectory.recipes, [ mock_recipe ] )
        self.assertEqual( trajectory.xdatcar, mock_xdatcar )
        self.assertEqual( trajectory.config_numbers, [ 0, 1 ] )
        self.assertEqual( trajectory.configurations, mock_configurations )

class TestTrajectoryHelperFunctions( unittest.TestCase ):

    def test_read_config_numbers_from_xdatcar( self ):
        example_file = "Direct configuration=  10\nDirect configuration=   20\n"
        with patch( 'builtins.open', mock_open( read_data=example_file ), create=True ) as m:
            self.assertEqual( read_config_numbers_from_xdatcar( 'foo' ), [ 10, 20 ] )

if __name__ == '__main__':
    unittest.main()
