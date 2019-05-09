from .atom import Atom
from .symmetry_measure import symmetry_measures_from_coordination
from .orientation_parameters import cos_theta
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import AbstractGeometry, symmetry_measure
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometries import AllCoordinationGeometries
from pymatgen.util.coord import pbc_shortest_vectors
import numpy as np
from scipy.spatial import ConvexHull
from itertools import permutations, combinations
import vg

class CoordinationPolyhedron:

    def __init__( self, central_atom, vertices, label=None ):
        """
        Initialise a CoordinationPolyhedron object.
 
        Args:
            central_atom (Atom): the central atom.
            vertices (list(Atom)): A list of atoms that define the coordination environment.
            label (:obj:`str`, optional): An optional string used to label this coordination polyhedron.
                if the label is not defined, the label of the central atom will be used.

        Returns:
            None
        """
        self.central_atom = central_atom
        self.central_atom.in_polyhedra.append( self )
        self.vertices = sorted( vertices )
        for v in self.vertices:
            v.in_polyhedra.append( self )
        if label:
            self.label = label
        else:
            self.label = central_atom.label
        for vertex, neighbour_list in zip( self.vertices, self.construct_edge_graph().values() ):
            if not vertex.neighbours:
                vertex.neighbours = {}
            vertex.neighbours[ self.index ] = neighbour_list
        self._abstract_geometry = self.construct_abstract_geometry()

    def __repr__( self ):
        """
        String representation of a Polyhedron object.

        The output includes the polyhedron label (if this is set), and
        information about the central and vertex atoms. For each atom
        the output includes::

            atom_index [ x y z ] atom_species

        Examples:

            >>>> print(polyhedron)
            Coordination Polyhedron 4c
            255 [12.71362322 17.90999634 12.74490767] S
            ----------
            31 [12.46919306 20.2317206  12.2641591 ] Li
            55 [13.0016308  17.39863735 10.46318072] Li
            71 [10.4034848  18.18407515 12.43873978] Li
            103 [12.17924193 15.66932958 13.34077502] Li
            159 [13.24242002 18.43469275 15.02193658] Li
            175 [15.02830461 17.60091516 12.52079631] Li

        """
        if self.label:
            to_return = 'Coordination Polyhedron {}\n'.format( self.label ) 
        else:
            to_return = 'Coordination Polyhedron\n'
        to_return += '{}\n'.format( self.central_atom )
        to_return += '----------\n'
        for v in self.vertices:
            to_return += '{}\n'.format( v )
        return to_return

    def intersection( self, other_polyhedron ):
        """Returns a list of atom indices for vertex atoms shared with another polyhedron.

        Args:
            other_polyhedron (:obj:`CoordinationPolyhedron`): The other coordination polyhedron.

        Returns:
            (list(int)): List of shared vertex indices.

        """
        return list( set( self.vertex_indices ) & set( other_polyhedron.vertex_indices ) )
       
    @property
    def vertex_indices( self ):
        return [ v.index for v in self.vertices ]

    @property
    def vertex_vectors( self ):
        return self._abstract_geometry.points_wocs_ctwocc()

    @property
    def vertex_coords( self ):
        return np.array( [ v.coords for v in self.vertices ] )
 
    @property
    def coordination_number( self ):
        return len( self.vertices )

    @property
    def index( self ):
        return self.central_atom.index

    @property
    def edge_graph( self ):
        to_return = {}
        for v in self.vertices:
            to_return[ v.index ] = v.neighbours[ self.index ]
        return to_return
  
    @property
    def abstract_geometry( self ):
        return self._abstract_geometry
 
    def construct_abstract_geometry( self ):
        """
        Returns the polyhedron as a ``pymatgen`` :obj:`AbstractGeometry` object.
        """
        return AbstractGeometry( central_site=self.central_atom.coords, 
                                 bare_coords=self.minimum_image_vertex_coordinates(), 
                                 include_central_site_in_centroid=False )

    @property
    def symmetry_measure( self ):
        if self.coordination_number not in symmetry_measures_from_coordination:
            raise ValueError( 'No symmetry measure objects for coordination number of {}'.format( self.coordination_number ) )
        msm = {}
        for string, sm in symmetry_measures_from_coordination[ self.coordination_number ].items():
            msm[ string ] = sm.minimum_symmetry_measure( self.abstract_geometry )
        return msm 

    @property
    def best_fit_geometry( self ):
        psm = self.symmetry_measure
        best_fit = min( psm, key=psm.get )
        return { 'geometry': best_fit, 'symmetry_measure': psm[ best_fit ] }

    def minimum_image_vertex_coordinates( self ):
        vertex_frac_coords = [ v.frac_coords for v in self.vertices ]
        pbc_vectors = pbc_shortest_vectors( self.central_atom.lattice, self.central_atom.frac_coords, vertex_frac_coords )[0]
        vertex_minimum_image_coords = [ self.central_atom.coords + v for v in pbc_vectors ]
        return vertex_minimum_image_coords

    def faces( self ):
        """
        Args:
            None

        Returns:
            (dict(int:list[int])
        """
        return [ [ self.vertex_indices[v] for v in simplex ] 
                 for simplex in merge_coplanar_simplices( self.convex_hull() ) ]

    def convex_hull( self ):
        return ConvexHull( self.minimum_image_vertex_coordinates() )

    def construct_edge_graph( self ):
        connected_vertices = { i : set() for i in range( self.coordination_number ) }
        if self.coordination_number > 3:
            convex_hull = self.convex_hull()
            for m in merge_coplanar_simplices( convex_hull ):
                if len(m) == 3:
                    for r in range(3):
                        rotated_simplex = np.roll(m,r)
                        connected_vertices[ rotated_simplex[0] ].add( rotated_simplex[1] )
                        connected_vertices[ rotated_simplex[0] ].add( rotated_simplex[2] )
                else: # non-triangular face with > 4 vertices. This will be a composite of more than one simplex.
                    component_simplices = []
                    for s in convex_hull.simplices:
                        if np.all( [ i in m for i in s ] ):
                            component_simplices.append( s )
                    # common elements are linked along an internal edge.
                    for s_roll in range( len( component_simplices ) ):
                        rotated_component_simplices = np.roll( component_simplices, s_roll, axis=0 )
                        this_simplex = rotated_component_simplices[0]
                        other_simplices = rotated_component_simplices[1:]
                        for roll in range(3):
                            internal_edge = True
                            rotated_simplex = np.roll( this_simplex, roll )
                            edge = [ rotated_simplex[0], rotated_simplex[1] ]
                            if not np.all( [ i in np.unique( other_simplices ) for i in edge ] ):
                                connected_vertices[ edge[0] ].add( edge[1] )
                            edge = [ rotated_simplex[0], rotated_simplex[2] ]
                            if not np.all( [ i in np.unique( other_simplices ) for i in edge ] ):
                                connected_vertices[ edge[0] ].add( edge[1] )
        else:
            for roll in range( self.coordination_number ):
                rotated_list = np.roll( list( range( self.coordination_number ) ), roll )
                for i in rotated_list[1:]:
                    connected_vertices[ rotated_list[0] ].add( i )
        edge_list = {}
        for i in range( self.coordination_number ):
            edge_list[ self.vertex_indices[i] ] = [ self.vertex_indices[v] for v in connected_vertices[i] ] 
        return edge_list

    def vertex_distances( self, vertex_labels=False ):
        """
        Returns a list of distances from the central atom to the vertex atoms.

        Args:
            vertex_labels (:obj:`bool`, optional): If set to ``True`` this function will
                return labels for the vertices with each corresponding distance.
                Default = ``False``.

        Returns:
            list (float): A list of atomic separations. If ``vertex_labels=True`` the
                label for each vertex atom will also be returned with each corresponding distance.

        """ 
        distances = [ self.central_atom.site.distance( v.site ) for v in self.vertices ]
        if vertex_labels:
            labels = [ v.label for v in self.vertices ]
            return list( zip( distances, labels ) )
        else:
            return distances

    def equal_vertices( self, other ):
        """
        Test whether this :obj:`CoordinationPolyhedron` has vertices with the same labels as
        another :obj:`CoordinationPolyhedron`.

        Args:
            other (:obj:`CoordinationPolyhedron`): The other :obj:`CoordinationPolyhedron`.

        Returns:
            (bool): True / False.

        """
        return self.vertex_indices == other.vertex_indices

    def equal_edge_graph( self, other ):
        """
        Test whether this :obj:`CoordinationPolyhedron` has the same edge graph as
        another :obj:`CoordinationPolyhedron`.

        Args:
            other (:obj:`CoordinationPolyhedron`): The other :obj:`CoordinationPolyhedron`.

        Returns:
            (bool): True or False.

        """
        return self.edge_graph == other.edge_graph

    def equal_members( self, other ):
        """
        Test whether this :obj:`CoordinationPolyhedron` has the same member atoms
        as another :obj:`CoordinationPolyhedron`.

        Args:
            other (:obj:`CoordinationPolyhedron`): The other :obj:`CoordinationPolyhedron`.

        Returns:
            (bool): True or False.

        """
        equal_central_atom = self.central_atom == other.central_atom
        equal_vertex_atoms = self.vertices == other.vertices
        return equal_central_atom & equal_vertex_atoms

    def __eq__( self, other ):
        """
        Two :obj:`CoordinationPolyhedron` objects are considered equal if they
        have equal edge graphs.

        Args:
            other (:obj:`CoordinationPolyhedron`): The other :obj:`CoordinationPolyhedron`.

        Returns:
            (bool): True or False.

        """
        return self.equal_edge_graph( other )
    
    def vertex_vector_projections( self, vectors ):
        """
        Calculate the projection of each centroid-to-vertex vector on one or more input vectors..

        Args:
            vectors (np.array): A Nx3 numpy array, where each row is a vector used
                                to calculate the projection. `vectors` can also be 
                                a single length 3 array.

        Returns:
            (np.array): A (N_vertex x N_vector) dimension numpy array.

        """
        if len( vectors.shape ) == 1:
            vectors = np.array( [ vectors ] )
        to_return = []
        for point in self.abstract_geometry.points_wocs_ctwocc():
            for vec in vectors:
                to_return.append( cos_theta( vec, point ) )
        return np.array( to_return ).reshape(-1,vectors.shape[0])
 
    def coordination_distances( self ):
        """
        List of distances from the central atom to the vertex atoms.

        Args:
            None

        Returns:
            (list): List of distances.

        """ 
        return [ self.central_atom.site.distance( v.site ) for v in self.vertices ]

    def angles( self ):
        """
        List of all vertex-centre-vertex angles.

        Args:
            None

        Returns:
             (list): List of angles.

        """
        return [ vg.angle( p1, p2 ) for p1, p2 in combinations( self.vertex_vectors, 2 ) ]

    def vertex_vector_orientations( self, units='degrees', return_distance=False ):
        """Returns the angular orientations of each centroid-to-vertex vector.

        The orientation is defined by two angles, theta and phi. 
        Theta is the angle with respect to [ 0, 0, 1 ] and ranges from 0 to 180 degrees. 
        Phi is the angle with respect to [ 1, 0, 0 ] and ranges from -180 to +180 degrees.

        Args:
            units (:obj:`str`, optional): Optionally select the units for the calculated angles.
                                          Options are `degrees` or `radians`. 
                                          Default is `degrees`.
            return_distance (:obj:`bool`, optional): Optionally also return the distance. 

        Returns:
            (list(tuple)): A list of `(theta,phi)` tuple pairs.

        """
        vg_units = { 'degrees': 'deg', 
                     'radians': 'rad' }
        theta = [ vg.angle( np.array( [ 0.0, 0.0, 1.0 ] ), point, units=vg_units[ units ] ) 
                      for point in self.vertex_vectors ]
        phi = [ vg.signed_angle( np.array( [ 1.0, 0.0, 0.0 ] ), point, 
                                 look=np.array( [ 0.0, 0.0, 1.0 ] ), units=vg_units[ units ] )
                    for point in self.vertex_vectors ]
        if return_distance:
            distance = [ vg.magnitude( point ) for point in self.vertex_vectors ]
            return list( zip( theta, phi, distance ) )
        return list( zip( theta, phi ) )

    @property
    def volume( self ):
        """
        Volume of this polyhedron.

        Args:
            None

        Returns:
            (float): The volume.

        """
        return self.convex_hull().volume

    @classmethod
    def from_sites( cls, central_site, vertex_sites, label=None ):
        """
        Create a :obj:`CoordinationPolyhedron` from a set of `pymatgen` :obj:`PeriodicSite` objects.

        Args:
            central_site (:obj:`pymatgen.PeriodicSite`): A `pymatgen` :obj:`PeriodicSite` object describing an atom at the nominal centre of the polyhedron.
            vertex_sites (list[:obj:`pymatgen.PeriodicSite`): A list of `pymatgen` :obj`PeriodicSite` objects describing the atoms at the vertices.
            label (:obj:`str`, optional): An optional string used to label this coordination polyhedron.

        Returns:
            (:obj:`CoordinationPolyhedron`): The :obj:`CoordinationPolyhedron` object.
        """
        vertices = [ Atom( i, s ) for i, s in enumerate( vertex_sites ) ]
        central_atom = Atom( -1, central_site )
        return cls( central_atom=central_atom, vertices=vertices, label=label )
        
    def vertices_by_indices( self, vertex_indices ):
        """
        Select a subset of vertices from this polyhedron with a list of vertex indices.

        Args:
            vertex_indices (list): List of vertex indices (int).

        Returns:
            (list): A list of :obj:`Atom` objects containing the matching vertices.

        """
        return [ v for v in self.vertices if v.index in vertex_indices ]

def merge_coplanar_simplices( complex_hull, tolerance=0.1 ):
    triangles_to_merge = []
    # TODO: there has to be a better way of doing this pairwise loop, e.g. using itertools.permutations
    for i, e1 in enumerate( complex_hull.equations ):
        for j, e2 in enumerate( complex_hull.equations[i+1:], i+1 ):
            if np.all( e1 == e2 ):
                continue
            dr = e1 - e2
            distance = np.dot( dr, dr )
            if distance < tolerance:
                triangles_to_merge.append( [ i, j ] )
    merged_simplices = []
    for i, s in enumerate( complex_hull.simplices ):
        if i not in np.unique( triangles_to_merge ):
            merged_simplices.append( s )
    for i, j in triangles_to_merge:
        merged_simplices.append( np.unique( [ complex_hull.simplices[i], complex_hull.simplices[j] ] ) ) 
    return merged_simplices # note: this simplex is not ordered: should not be used to construct the edge_graph.
