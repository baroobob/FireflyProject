#!/usr/local/bin/python
# written for python 2.7.8

"""
This class modifies (a.k.a. warps) images from OpenGL for display on a
hemispherical screen in a virtual reality system.  A hemispherical mirror is
used to allow a single projector to achieve a very wide field of view.  The
goal in our mouse experiments is to achieve a minimum field of view of -20
degrees to 60 degrees verically and 270 degrees horizontally.  The OpenGL
images are modified to eliminate the distortion introduced by the hemispherical
mirror and the hemispherical screen.  This is achieved by a pixel level mapping
which sets the RGB values for each projector pixel using the RGB values of
the pixel in the OpenGL image which is in the same direction from the viewer's
point of view.  The viewer in the dome display is the mouse and the viewer in
OpenGL is a virtual camera.  
"""

DEBUG = True

if DEBUG:
    from numpy import arctan, arctan2, arccos, where
    import matplotlib.pyplot as plot
    from matplotlib.backends.backend_pdf import PdfPages

from numpy import array, ones, zeros, dstack, linalg, dot, cross
from numpy import sqrt, sin, cos, tan, pi
from numpy import uint8
from random import randint
from PIL import Image

class DomeProjection:
    """
    The dome projection class describes the geometry of our dome, spherical
    mirror, and projector along with the geometry of the associated OpenGL
    virtual camera and screen.
    All vectors in the OpenGL world are relative to the virtual camera and
    all vectors in the dome display setup are relative to the center of the
    hemispherical mirror.
    """
    def __init__(self,
                 screen_height = [1.0, 1.0, 1.0],
                 screen_width = [1.4, 1.4, 1.4],
                 distance_to_screen = [0.5, 0.5, 0.5],
                 pitch = [30, 30, 30],
                 yaw = [-90, 0, 90],
                 roll = [0, 0, 0],
                 image_pixel_height = [200, 200, 200],
                 image_pixel_width = [280, 280, 280],
                 projector_pixel_height = 720,
                 projector_pixel_width = 1280,
                 first_projector_image = [[-0.080, 0.436, 0.137],
                                          [0.080, 0.436, 0.137],
                                          [0.080, 0.436, 0.043],
                                          [-0.080, 0.436, 0.043]],
                 second_projector_image = [[-0.115, 0.265, 0.186],
                                           [0.115, 0.265, 0.186],
                                           [0.115, 0.265, 0.054],
                                           [-0.115, 0.265, 0.054]],
                 mirror_radius = 0.215,
                 dome_center = [0, 0.138, 0.309],
                 dome_radius = 0.603,
                 animal_position = [0, 0.06, 0.61]
                 ):
                 #mirror_radius = 0.223,

        """
        Parameters:
        ----------------------------
        @param screen_height:
            A list of the heights of each OpenGL screen in arbitrary units.
        @param screen_width:
            A list of the widths of each OpenGL screen in arbitrary units.
        @param distance_to_screen:
            A list of the distances from each OpenGL virtual camera to its
            respective screen in arbitrary units.
        @param pitch:
            A list of the angles between the xy plane and each camera's viewing
            direction in degrees (the pitch in aeronautical terms).
        @param yaw:
            A list of the angles in the xy plane between each camera's viewing
            direction and the y-axis (the yaw in aeronautical terms).
        @param roll:
            A list of the angles of rotation of each camera image relative to
            the xy plane (the roll in aeronautical terms).
        @param image_pixel_height:
            A list of the number of vertical pixels in each OpenGL image.
        @param image_pixel_width:
            A list of the number of horizontal pixels in each OpenGL image.
        @param projector_pixel_height:
            The number of vertical pixels in the projector image.
        @param projector_pixel_width:
            The number of horizontal pixels in the projector image.
        @param first_projector_image:
            A list of four (x,y1,z) points, starting top left and proceeding
            clockwise, that specifies the corners of the projector's image
            at a distance y1 from the center of the mirror.
        @param second_projector_image:
            A list of four (x,y2,z) points, starting top left and proceeding
            clockwise, that specifies the corners of the projector's image
            at a distance y2 from the center of the mirror.
        @param mirror_radius:
            The radius of the mirror in arbitrary units.
        @param dome_center:
            An (x,y,z) vector from the center of the mirror to the center of
            the dome.
        @param dome_radius:
            The radius of the dome in arbitrary units.
        @param animal_position:
            An (x,y,z) vector from the center of the mirror to the position
            of the animal's eyes.
        """

        #######################################################################
        # Properties passed in as arguments
        #######################################################################
        self._screen_height = screen_height
        self._screen_width = screen_width
        self._distance_to_screen = distance_to_screen
        self._pitch = [i * pi/180.0 for i in pitch]
        self._yaw = [i * pi/180.0 for i in yaw]
        self._roll = [i * pi/180.0 for i in roll]
        self._image_pixel_height = image_pixel_height
        self._image_pixel_width = image_pixel_width
        self._projector_pixel_height = projector_pixel_height
        self._projector_pixel_width = projector_pixel_width
        self._first_projector_image = first_projector_image
        self._second_projector_image = second_projector_image
        self._mirror_radius = mirror_radius
        self._dome_center = dome_center
        self._dome_radius = dome_radius
        self._animal_position = animal_position

        #######################################################################
        # Properties used to share results between method calls
        #######################################################################

        # Start search in the middle of the projector's bottom row of pixels
        self._projector_pixel_row = projector_pixel_height - 1
        self._projector_pixel_col = projector_pixel_width/2

        #######################################################################
        # Properties calculated from arguments
        #######################################################################
        """
        Calculate the vectors to the center of each screen along with unit
        vectors that indicate the directions for increasing row and column
        numbers. These vectors will make it very easy to calculate the row and
        column of a pixel given the direction from the viewer to that pixel.
        """
        self._vector_to_screen = []
        self._row_vector = []
        self._col_vector = []
        for screen in range(len(distance_to_screen)):
            yaw = self._yaw[screen]
            pitch = self._pitch[screen]
            roll = self._roll[screen]
            x = (distance_to_screen[screen] * sin(yaw) * cos(pitch))
            y = (distance_to_screen[screen] * cos(yaw) * cos(pitch))
            z = distance_to_screen[screen] * sin(pitch)
            self._vector_to_screen.append(array([x, y, z]))
            # Create a column vector that will be used as a basis vector to
            # find the column number of pixels in images from this camera.
            # Supporting image rotation makes this a bit confusing.  When
            # roll=0, the cross product is between vector_to_screen and
            # [0, 0, 1], the unit vector in the positive z direction.
            col_vector = cross(self._vector_to_screen[screen],
                               array([sin(roll)*cos(yaw),
                                      sin(roll)*sin(yaw),
                                      cos(roll)]))
            col_vector = col_vector / linalg.norm(col_vector)
            self._col_vector.append(col_vector)
            # Create a row vector that will be used as a basis vector to
            # find the row number of pixels in images from this camera.
            row_vector = cross(self._vector_to_screen[screen], col_vector)
            row_vector = row_vector / linalg.norm(row_vector)
            self._row_vector.append(row_vector)

        """
        Calculate the unit vectors (aka directions) that point from
        OpenGL's virtual camera towards all of the OpenGL image pixels.
        All vectors are relative to OpenGL's virtual camera which
        is looking down the positive y-axis.
        """
        self._camera_view_directions = \
            flat_display_directions(screen_height[0],
                                    screen_width[0],
                                    image_pixel_height[0],
                                    image_pixel_width[0],
                                    distance_to_screen[0],
                                    self._pitch[0])

        """
        Calculate the unit vectors (directions) from the animal inside the dome
        towards the projection of each projector pixel on to the dome.
        """
        self._animal_view_directions = self._dome_display_directions()

        """
        Build lists of the OpenGL image pixels that contribute to each
        projector pixel.
        """
        self._contributing_pixels = self._calc_contributing_pixels()



    ###########################################################################
    # Class methods
    ###########################################################################

    def _dome_display_directions(self):
        """
        Return the unit vectors (directions) from the viewer inside the dome
        towards the projection of each projector pixel on to the dome.
        All vectors used in these calculations are relative to the center of
        the hemispherical mirror.  The projector is on the positive y-axis
        (but projecting in the -y direction) and its projected image is assumed
        to be horizontally centered on the mirror.
        """

        # Calculate the position of the projector's focal point.
        projector_focal_point = self._calc_projector_focal_point()

        if DEBUG:
            self._projector_focal_point = projector_focal_point

        """
        Calculate the unit vectors (directions) from the projector's focal
        point towards the mirror for each projector pixel.  This calculation
        assumes second_projector_image has the same width at the top and bottom.
        """
        # calculate image height and width
        top_right_x = self._second_projector_image[1][0]
        top_left_x = self._second_projector_image[0][0]
        top_left_z = self._second_projector_image[0][2]
        bottom_left_z = self._second_projector_image[3][2]

        image_height = top_left_z - bottom_left_z
        image_width = top_right_x - top_left_x

        # calculate distance from projector to image
        image_y = self._second_projector_image[0][1]
        projector_y = projector_focal_point[1]

        distance_to_image = image_y - projector_y

        # calculate vertical offset of image relative to projector
        projector_z = projector_focal_point[2]

        vertical_offset = bottom_left_z - projector_z + image_height/2

        # calculate the directions for each projector pixel
        self._projector_pixel_directions = \
            flat_display_directions(image_height,
                                    image_width,
                                    self._projector_pixel_height,
                                    self._projector_pixel_width,
                                    distance_to_image,
                                    vertical_offset)

        # Flip the sign of the x-values because projection is in -y direction
        self._projector_pixel_directions *= array([-1, 1, 1])

        """
        Complete the triangle consisting of:
            1.  the vector from the center of the mirror to the projector's
                focal point (completely specified)
            2.  the vector from the projector's focal point to the mirror for
                the given projector pixel (known direction, unknown length)
            3.  the vector from the center of the mirror to the point on the
                mirror where the vector in 2 hits the mirror (known length,
                unknown direction)
        Vector 3 is normal to the mirror's surface at the point of reflection
        and is used to calculate the direction of the reflected light.
        """
        # solve quadratic equation for y-component of vector 2
        px = projector_focal_point[0]
        py = projector_focal_point[1]
        pz = projector_focal_point[2]
        pdx = self._projector_pixel_directions[:, :, 0]
        pdy = self._projector_pixel_directions[:, :, 1]
        pdz = self._projector_pixel_directions[:, :, 2]
        a = pdx**2 + pdy**2 + pdz**2
        b = 2*px*pdx + 2*py*pdy + 2*pz*pdz
        c = px**2 + py**2 + pz**2 - self._mirror_radius**2
        projector_mask = zeros([self._projector_pixel_height,
                                self._projector_pixel_width], dtype=int)
        incident_light_vectors = zeros([self._projector_pixel_height,
                                        self._projector_pixel_width, 3])
        for i in range(self._projector_pixel_height):
            for j in range(self._projector_pixel_width):
                """
                The vector will intersect the sphere twice.  Pick the root
                for the shorter vector.
                """
                d_squared = b[i, j]**2 - 4*a[i, j]*c
                if d_squared >= 0:
                    """
                    For projector pixels that hit the mirror, calculate the
                    incident light vector and set the mask to one.
                    """
                    d = sqrt(d_squared)
                    r = min([(-b[i, j] + d) / (2*a[i, j]),
                         (-b[i, j] - d) / (2*a[i, j])])
                    x = r*pdx[i, j]
                    y = r*pdy[i, j]
                    z = r*pdz[i, j]
                    incident_light_vectors[i, j] = array([x, y, z])
                    projector_mask[i, j] = 1

        mirror_radius_vectors = projector_focal_point + incident_light_vectors
        mirrorUnitNormals = mirror_radius_vectors / self._mirror_radius

        if DEBUG:
            # create properties for intermediate results
            self._projector_mask = projector_mask
            self._incident_light_vectors = incident_light_vectors
            self._mirror_radius_vectors = mirror_radius_vectors
            self._mirrorUnitNormals = mirrorUnitNormals

        """
        Use the incident_light_vectors and the mirrorUnitNormals to calculate
        the direction of the reflected light.
        """
        reflectedLightDirections = zeros([self._projector_pixel_height,
                                          self._projector_pixel_width, 3])
        for i in range(self._projector_pixel_height):
            for j in range(self._projector_pixel_width):
                if projector_mask[i, j] == 1:
                    u = mirrorUnitNormals[i, j]
                    reflectedLightVector = \
                        -2*dot(incident_light_vectors[i, j], u)*u \
                        + incident_light_vectors[i, j]
                    reflectedLightDirections[i, j] = \
                        reflectedLightVector/linalg.norm(reflectedLightVector)

        if DEBUG:
            self._reflectedLightDirections = reflectedLightDirections

        """
        Complete the triangle again to get the reflected light vectors.
        The known vector is from the center of the dome to the reflection
        point on the mirror (calculated as mirror_radius_vectors - dome_center)
        and the length of the vector with unknown direction is the dome radius.
        """
        # solve quadratic for y-component of reflected light vectors
        rpx = mirror_radius_vectors[:, :, 0] - self._dome_center[0]
        rpy = mirror_radius_vectors[:, :, 1] - self._dome_center[1]
        rpz = mirror_radius_vectors[:, :, 2] - self._dome_center[2]
        rldx = reflectedLightDirections[:, :, 0]
        rldy = reflectedLightDirections[:, :, 1]
        rldz = reflectedLightDirections[:, :, 2]
        a = rldx**2 + rldy**2 + rldz**2
        b = 2*rpx*rldx + 2*rpy*rldy + 2*rpz*rldz
        c = rpx**2 + rpy**2 + rpz**2 - self._dome_radius**2
        reflected_light_vectors = zeros([self._projector_pixel_height,
                                         self._projector_pixel_width, 3])
        for i in range(self._projector_pixel_height):
            for j in range(self._projector_pixel_width):
                if projector_mask[i, j] == 1:
                    # For projector pixels that hit the mirror,
                    # take the solution with positive vector length.
                    d = sqrt(b[i, j]**2 - 4*a[i, j]*c[i, j])
                    r = max([(-b[i, j] + d) / (2*a[i, j]),
                             (-b[i, j] - d) / (2*a[i, j])])
                    x = r*rldx[i, j]
                    y = r*rldy[i, j]
                    z = r*rldz[i, j]
                    reflected_light_vectors[i, j] = [x, y, z]

        if DEBUG:
            self._reflected_light_vectors = reflected_light_vectors

        """
        Now use the vectors of the reflected light, reflection position on the
        mirror, and animal position to calculate the animal's viewing direction
        for each projector pixel.
        """
        animal_view_directions = zeros([self._projector_pixel_height,
                                        self._projector_pixel_width, 3])
        for i in range(self._projector_pixel_height):
            for j in range(self._projector_pixel_width):
                if projector_mask[i, j] == 1:
                    # For projector pixels that hit the mirror,
                    # calculate the view direction for the animal.
                    animal_view_vector = (reflected_light_vectors[i, j]
                                        + mirror_radius_vectors[i, j]
                                        - self._animal_position)
                    magnitude = linalg.norm(animal_view_vector)
                    animal_view_directions[i, j] = animal_view_vector/magnitude

        return animal_view_directions


    def _calc_projector_focal_point(self):
        """
        Calculate the position of the projector's focal point.  The projector
        image is horizontally centered on the mirror so the x-component
        of the focal point's position is zero.  Calculate the intersection
        point of the lines along the top and bottom of the projected light to
        get the focal point's y and z coordinates.
        """
        # calculate slope of line along top of projected light
        upper_z1 = self._first_projector_image[0][2]
        upper_z2 = self._second_projector_image[0][2]
        y1 = self._first_projector_image[0][1]
        y2 = self._second_projector_image[0][1]
        upperSlope = (upper_z2 - upper_z1)/(y2 - y1)

        # calculate slope of line along bottom of projected light
        lower_z1 = self._first_projector_image[2][2]
        lower_z2 = self._second_projector_image[2][2]
        lowerSlope = (lower_z2 - lower_z1)/(y2 - y1)

        # calculate y and z where the lines intersect
        a = array([[upperSlope, -1], [lowerSlope, -1]])
        b = array([upperSlope*y1 - upper_z1, lowerSlope*y1 - lower_z1])
        [y, z] = linalg.solve(a, b)
        projector_focal_point = array([0, y, z])

        return projector_focal_point


    def _calc_contributing_pixels(self):
        """
        Use the direction for each projector pixel to calculate the nearest
        OpenGL pixel and use its RGB values for the projector pixel.  
        """

        # This 2D list of lists contains the list of OpenGL pixels
        # that contribute to each projector pixel.
        contributing_pixels = \
            [[[] for i in range(self._projector_pixel_width)]
             for j in range(self._projector_pixel_height)]
        # Calculate center pixels, pixel spacing and direction vectors for each
        # screen.
        screens = range(len(self._distance_to_screen))
        row_center = [self._image_pixel_height[i] / 2 for i in screens]
        row_spacing = [float(self._screen_height[i])
                            / self._image_pixel_height[i] for i in screens]
        col_center = [self._image_pixel_width[i] / 2 for i in screens]
        col_spacing = [float(self._screen_width[i])
                            / self._image_pixel_width[i] for i in screens]
        vector_to_screen = self._vector_to_screen
        distance_to_screen = [linalg.norm(v) for v in vector_to_screen]
        direction_to_screen = [vector_to_screen[i] / distance_to_screen[i]
                               for i in screens]
        for row in range(self._projector_pixel_height):
            for col in range(self._projector_pixel_width):
                if self._projector_mask[row, col] == 1:
                    """
                    For each projector pixel that hits the mirror, use the
                    direction in which the animal sees this pixel to find the
                    OpenGL pixel which has the closest direction from the
                    virtual camera's point of view.  The RGB values of this
                    OpenGL pixel will be used for this projector pixel.
                    """
                    # Calculate the magnitude required for a vector in this
                    # direction to hit the nearest OpenGL screen.
                    direction = self._animal_view_directions[row, col]
                    # Find the nearest OpenGL screen
                    screen = 0
                    direction_dot_direction_to_screen = 0
                    for i in screens:
                        dp = direction.dot(direction_to_screen[i])
                        if dp > direction_dot_direction_to_screen:
                            direction_dot_direction_to_screen = dp
                            screen = i
                    if direction_dot_direction_to_screen > 0:
                        """
                        Ignore cases where the dot product of direction and
                        direction_to_screen is negative.  These cases project
                        the image to a second, incorrect location on the dome.
                        """
                        # Calculate the full vector from the unit vector in this
                        # direction and use it to find the row and column numbers
                        # of the OpenGL pixel.
                        magnitude = (distance_to_screen[screen]
                                     / direction_dot_direction_to_screen)
                        x = magnitude * direction[0]
                        y = magnitude * direction[1]
                        z = magnitude * direction[2]
                        on_screen_vector = (array([x, y, z])
                                            - vector_to_screen[screen])
                        r = (row_center[screen]
                             + on_screen_vector.dot(self._row_vector[screen])
                             / row_spacing[screen])
                        c = (col_center[screen]
                             + on_screen_vector.dot(self._col_vector[screen])
                             / col_spacing[screen])
                        # make sure the pixel is inside the OpenGL image
                        if (r >= 0 and r < self._image_pixel_height[screen]
                            and c >= 0 and c < self._image_pixel_width[screen]):
                            contributing_pixels[row][col].append([screen, r, c])

        return contributing_pixels


    def _find_contributing_pixels(self):
        """
        For each OpenGL image pixel use the directions for the camera view
        and the animal view to find the projector pixel with the closest
        direction.  Then add that OpenGL pixel to the projector pixel's list
        of contributing pixels.
        """

        # This 2D list of lists contains the list of OpenGL pixels
        # that contribute to each projector pixel.
        contributing_pixels = \
            [[[] for i in range(self._projector_pixel_width)]
             for j in range(self._projector_pixel_height)]
        row = 0
        while row < self._image_pixel_height:
            for col in range(self._image_pixel_width):
                """
                For each OpenGL image pixel, determine which projector
                pixel has the closest direction.
                """
                [r, c] = self._find_closest_projector_pixel(row, col)
                contributing_pixels[r][c].append([row, col])
            row = row + 1
            for col in range(self._image_pixel_width - 1, -1, -1):
                """
                Go through the pixels in a serpentine pattern so that the
                current pixel is always close to the last pixel.  This way the
                search algorithm can use the last result as its starting point.
                """
                [r, c] = self._find_closest_projector_pixel(row, col)
                contributing_pixels[r][c].append([row, col])
            row = row + 1

        return contributing_pixels


    def _find_closest_projector_pixel(self, row, col):
        """
        For the OpenGL image pixel specified by row and col use the directions
        in self._camera_view_directions and self._animal_view_directions to find the
        projector pixel which has the closest direction and return its row and
        column in a list.  This is done using a search method rather than
        calculating the dot product for every projector pixel.
        """
        camera_direction = self._camera_view_directions[row, col]

        # Start with the last projector pixel
        r = self._projector_pixel_row
        c = self._projector_pixel_col

        while self._projector_mask[r, c] == 0:
            # if the pixel doesn't hit the mirror, find one that does
            r = randint(self._projector_pixel_height)
            c = randint(self._projector_pixel_width)

        animalDirection = self._animal_view_directions[r, c]

        # Calculate dot product of this OpenGL pixel
        # with the last projector pixel.
        dp = dot(camera_direction, animalDirection)

        # Calculate dot product of this OpenGL pixel with the
        # neighboring projector pixels.
        [neighbor_dps, neighbors] = \
            self._calc_neighbor_dot_products(r, c, camera_direction)

        while max(neighbor_dps) > dp:
            """
            If the dot product with one of the neighboring projector pixels is
            larger then update r and c to that pixel and check its neighbors.
            Repeat until all neighbors have smaller (or equal) dot products.
            """
            dp = max(neighbor_dps)
            [r, c] = neighbors[neighbor_dps.index(dp)]
            [neighbor_dps, neighbors] = \
                self._calc_neighbor_dot_products(r, c, camera_direction)

        # Save projector pixel for next call
        self._projector_pixel_row = r
        self._projector_pixel_col = c
        return [r, c]


    def _calc_neighbor_dot_products(self, row, col, camera_direction):
        """
        For the projector pixel specified by row and col, calculate the dot
        product of all its neighbors with the given camera direction.  Return
        a list containing a list of the dot products and a list of the row and
        column for each corresponding pixel.
        """
        neighbors = []
        neighbor_dps = []

        # find neighbors
        row_above = [[-1, -1], [-1, 0], [-1, 1]]
        beside = [[0, -1], [0, 1]]
        row_below = [[1, -1], [1, 0], [1, 1]]
        offsets = row_above + beside + row_below
        for [dr, dc] in offsets:
            if row + dr >= 0 and row + dr < self._projector_pixel_height:
                if col + dc >= 0 and col + dc < self._projector_pixel_width:
                    neighbors.append([row + dr, col + dc])

        # calculate neighbor dot products
        for neighbor in neighbors:
            neighbor_direction = \
                self._animal_view_directions[neighbor[0], neighbor[1]]
            neighbor_dps.append(dot(camera_direction, neighbor_direction))

        return [neighbor_dps, neighbors]


    def _calc_fields_of_view(self):
        """
        Calculate the horizontal and vertical fields of view for both the
        OpenGL camera and the animal inside the dome.
        The calculation for the animal is not perfect because it looks for the
        extreme projector pixels instead of the extreme animal_view_directions
        for those projector pixels.
        """
        print "OpenGL's virtual camera has a horizontal field of view of:"
        left_x = self._camera_view_directions[0, 0, 0]
        left_y = self._camera_view_directions[0, 0, 1]
        right_x = self._camera_view_directions[0, image_pixel_width - 1, 0]
        right_y = self._camera_view_directions[0, image_pixel_width - 1, 1]
        left_theta = 180/pi*arctan2(left_y, left_x)
        right_theta = 180/pi*arctan2(right_y, right_x)
        print left_theta, "-", right_theta, "=", left_theta - right_theta
        print "OpenGL's virtual camera has a vertical field of view of:"
        bottom_y = self._camera_view_directions[image_pixel_height - 1, 0, 1]
        bottom_z = self._camera_view_directions[image_pixel_height - 1, 0, 2]
        top_y = self._camera_view_directions[0, 0, 1]
        top_z = self._camera_view_directions[0, 0, 2]
        bottom_phi = 180/pi*arctan2(bottom_y, bottom_z)
        top_phi = 180/pi*arctan2(top_y, top_z)
        print bottom_phi, "-", top_phi, "=", bottom_phi - top_phi
        print "The animal in the dome has a horizontal field of view of:"
        num_contributing_pixels = \
                array([[len(self._contributing_pixels[row][col])
                        for col in range(self._projector_pixel_width)]
                       for row in range(self._projector_pixel_height)])
        [non_empty_rows, non_empty_cols] = num_contributing_pixels.nonzero()
        '''
        what I want here is to find the left most pixel (row and col) and
        the right most pixel (row and col)
        '''

        left_most_pixel = \
                (non_empty_rows[where(non_empty_cols ==
                                      min(non_empty_cols))[0][0]],
                 min(non_empty_cols))
        print "left most pixel:", left_most_pixel

        right_most_pixel = \
                (non_empty_rows[where(non_empty_cols ==
                                      max(non_empty_cols))[0][0]],
                 max(non_empty_cols))
        print "right most pixel:", right_most_pixel

        upper_most_pixel = \
                (min(non_empty_rows),
                non_empty_cols[where(non_empty_rows ==
                                     min(non_empty_rows))[0][0]])
        print "upper most pixel:", upper_most_pixel

        lower_most_pixel = \
                (max(non_empty_rows),
                non_empty_cols[where(non_empty_rows ==
                                     max(non_empty_rows))[0][0]])
        print "lower most pixel:", lower_most_pixel

        left_x = self._animal_view_directions[left_most_pixel][0]
        left_y = self._animal_view_directions[left_most_pixel][1]
        right_x = self._animal_view_directions[right_most_pixel][0]
        right_y = self._animal_view_directions[right_most_pixel][1]
        left_theta = 180/pi*arctan2(left_y, left_x)
        right_theta = 180/pi*arctan2(right_y, right_x)
        print right_theta, "-", left_theta, "=", right_theta - left_theta
        print "The animal in the dome has a vertical field of view of:"
        bottom_y = self._animal_view_directions[lower_most_pixel][1]
        bottom_z = self._animal_view_directions[lower_most_pixel][2]
        top_y = self._animal_view_directions[upper_most_pixel][1]

        top_z = self._animal_view_directions[upper_most_pixel][2]
        bottom_phi = 180/pi*arctan2(bottom_y, bottom_z)
        top_phi = 180/pi*arctan2(top_y, top_z)
        print bottom_phi, "-", top_phi, "=", bottom_phi - top_phi


    def _debug_geometry(self, row, col):
        """
        Display images of intermediate results.
        """

        x_unit_vector = array([1, 0, 0])
        y_unit_vector = array([0, 1, 0])
        z_unit_vector = array([0, 0, 1])

        projector_y = self._projector_pixel_directions.dot(y_unit_vector)
        image = Image.fromarray(array(255*projector_y, dtype=uint8), mode='L')
        image.show()

        image = Image.fromarray(array(255*self._projector_mask,
                                     dtype=uint8), mode='L')
        image.show()

        animal_view_y = self._animal_view_directions.dot(y_unit_vector)
        y_image = Image.fromarray(array(255*abs(animal_view_y),
                                        dtype=uint8), mode='L')
        y_image.show()


    def _plot_image_outlines(self):
        """
        Plot the outline of the OpenGL image, the mirror, the warped image, and
        a projection of the animal's view onto a screen that is the same size
        and distance from the animal as the OpenGL screen.
        """

        ######################################################################
        # Plot the outline of the OpenGL screen in the x-z plane using units
        # of degrees so it is easy to determine the field of view.
        ######################################################################
        x_max = 180/pi*arctan(0.5*self._screen_width/self._distance_to_screen)
        x_min = -x_max
        x = [x_min, x_max, x_max, x_min, x_min]
        z_max = 180/pi*arctan(0.5*self._screen_height/self._distance_to_screen)
        z_min = -z_max
        z = [z_max, z_max, z_min, z_min, z_max]

        fig = plot.figure(1)
        axes = plot.subplot(111)
        axes.set_title('Outlines of OpenGL and warped, dome projected images')
        axes.set_xlim([-90, 90])
        axes.set_xticks(range(-90, 91, 15))
        axes.set_xlabel('Horizontal field of view (degrees)')
        axes.set_ylim([-90, 90])
        axes.set_yticks(range(-75, 91, 15))
        axes.set_ylabel('Vertical field of view (degrees)')
        axes.plot(x, z)

        ######################################################################
        # Plot the outline of the dome image projected onto the OpenGL screen
        ######################################################################

        # make a list of the pixels on the borders of the OpenGL image in
        # clockwise order starting at the top left
        top_row = [[0, col]
                   for col in range(self._image_pixel_width)]
        right_col = [[row, self._image_pixel_width - 1]
                      for row in range(self._image_pixel_height)]
        bottom_row = [[self._image_pixel_height - 1, col]
                      for col in range(self._image_pixel_width - 1, -1, -1)]
        left_col = [[row, 0]
                    for row in range(self._image_pixel_height - 1, -1, -1)]
        border_pixels = top_row + right_col + bottom_row + left_col

        # find the corresponding list of projector pixels which have the
        # closest directions
        warped_border_pixels = []
        for pixel in border_pixels:
            row = pixel[0]
            col = pixel[1]
            wb_pixel = self._find_closest_projector_pixel(row, col)
            warped_border_pixels.append(wb_pixel)

        # Project those pixels onto a flat screen in front of the animal. The
        # screen size should be the same as the OpenGL screen and the distance
        # from the animal to the screen should be the same as the distance from
        # the OpenGL camera to the OpenGL screen.

        x = []
        z = []
        for pixel in warped_border_pixels:
            row = pixel[0]
            col = pixel[1]
            y_component = self._distance_to_screen
            magnitude = y_component / self._animal_view_directions[row, col][1]
            x_component = magnitude * self._animal_view_directions[row, col][0]
            z_component = magnitude * self._animal_view_directions[row, col][2]
            x.append(180/pi*arctan(x_component / self._distance_to_screen))
            z.append(180/pi*arctan(z_component / self._distance_to_screen))

        # find distance 
        axes.plot(x, z)
        pdf = PdfPages('image_outlines.pdf')
        pdf.savefig(fig)
        pdf.close()
        plot.show()


    def warp_image_for_dome(self, images):
        """
        Take an RGB input image intended for display on a flat screen and
        produce an image for the projector that removes the distortions caused
        by projecting the image onto the dome using a spherical mirror.
        """
        pixels = []
        for i, image in enumerate(images):
            assert image.size == (self._image_pixel_width[i],
                                  self._image_pixel_height[i])
            pixels.append(array(image))

        warped_pixels = zeros([self._projector_pixel_height,
                               self._projector_pixel_width, 3], dtype=uint8)
        for row in range(self._projector_pixel_height):
            for col in range(self._projector_pixel_width):
                pixel_value = zeros(3)
                for pixel in self._contributing_pixels[row][col]:
                    pixel_value += pixels[pixel[0]][pixel[1], pixel[2]]
                n = len(self._contributing_pixels[row][col])
                if n > 0:
                    pixel_value = pixel_value/n
                warped_pixels[row][col] = array(pixel_value, dtype=uint8)

        return Image.fromarray(warped_pixels, mode='RGB')


    def _project_warped_image_to_screen(self, warped_image):
        """
        Take an input image intended for projection onto a dome via a
        spherical mirror and project it onto a flat screen.
        """
        assert warped_image.size == (self._projector_pixel_width,
                                     self._projector_pixel_height)

        warped_pixels = array(warped_image)
        pixels = zeros([self._image_pixel_height,
                        self._image_pixel_width, 3], dtype=uint8)
        for row in range(self._image_pixel_height):
            for col in range(self._image_pixel_width):
                """
                For each image pixel, find the closest projector pixel
                and use its RGB values.
                """
                projector_pixel = self._find_closest_projector_pixel(row, col)
                pp_row = projector_pixel[0]
                pp_col = projector_pixel[1]
                if self._projector_mask[pp_row, pp_col] == 1:
                    pixels[row, col] = warped_pixels[pp_row, pp_col]

        return Image.fromarray(pixels, mode='RGB')



###############################################################################
# Functions called by class methods
###############################################################################

def flat_display_directions(screen_height, screen_width, pixel_height,
                            pixel_width, distance_to_screen,
                            vertical_offset = 0, phi = 0):
    """
    Return unit vectors that point from the viewer towards each pixel
    on a flat screen display.  The display is along the positive y-axis
    relative to the viewer.  The positive x-axis is to the viewer's right
    and the positive z-axis is up.

    vertical_offset shifts the screen in the z-direction

    phi is the angle between the vector from the origin to the center of the
    image and the x-y plane
    """
    # Make matrices of projector row and column values
    rows = array([[float(i)]*pixel_width for i in
                  range(pixel_height)])
    columns = array([[float(i)]*pixel_height for i in
                     range(pixel_width)]).T

    """
    Calculate x and z values from column and row values so they
    are symmetric about the center of the image and scaled to the
    screen size.
    Also shift the z-values by z-offset and adjust y and z for rotation by phi.
    """

    x = screen_width*(columns/(pixel_width - 1) - 0.5)
    z = (distance_to_screen * sin(phi)
         + (0.5 - rows/(pixel_height - 1)) * screen_height * cos(phi)
         + vertical_offset)

    # y is the distance from the viewer to the screen
    y = (distance_to_screen * cos(phi)
         + (rows/(pixel_height - 1) - 0.5) * screen_height * sin(phi))
    r = sqrt(x**2 + y**2 + z**2)

    return dstack([x/r, y/r, z/r])


def plot_magnitude(array_of_vectors):
    """
    Plot an image of the magnitude of 3D vectors which are stored in a 2D
    array.  The luminance of each pixel is proportional to the normalized
    magnitude of its vector so larger magnitudes have lighter pixels.
    """
    dimensions = shape(array_of_vectors)
    #pixels = ones(dimensions, dtype=uint8)
    magnitudes = linalg.norm(array_of_vectors, axis=-1)
    normalizationFactor = max(magnitudes.flat)
    pixels = array(255*magnitudes/normalizationFactor, dtype=uint8)
    magnitude_image = Image.fromarray(pixels, mode='L')
    magnitude_image.show()

